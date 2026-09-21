"""Pre-LLM /fight smoke slash command."""

from __future__ import annotations

import re
from typing import Any

import os

import discord
from discord import app_commands

from battlebot.bot.audit import run_audited_command
from battlebot.common.db import connect_database
from battlebot.fight.decision_formatter import clamp_text, compact_field, format_decision, split_text_for_discord, structured_decision_output, sanitize_fight_card_item, is_dirty_fight_card_item
from battlebot.fight.llm_judge import judge_fight_packet
from battlebot.fight.personality import details as personality_details
from battlebot.fight.citations import linked_citations, source_panel, evidence_brief
from battlebot.fight.smoke_judge import smoke_judge_packet
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.profiles.search import format_search_results, search_characters
from battlebot.profiles.variants import CURATED_VARIANTS, split_variant_name
from battlebot.review.queue import enqueue_job


def available_forms_for_query(query: str) -> list[str]:
    if not query:
        return []
    parent, _ = split_variant_name(query)
    target = (parent or query).strip().casefold()
    forms = []
    for seed in CURATED_VARIANTS:
        if (
            seed.parent_name.casefold() == target
            or seed.name.casefold() == target
            or any(target == a.casefold() for a in seed.aliases.split("|") if a)
        ):
            if seed.variant_name and seed.variant_name not in forms:
                forms.append(seed.variant_name)
    return forms


class FormSelectionDropdown(discord.ui.Select):
    def __init__(self, contender_label: str, forms: list[str], custom_id: str):
        options = [discord.SelectOption(label="Base / Canonical Form", value="base", default=True)]
        for form in forms[:24]:
            options.append(discord.SelectOption(label=form[:100], value=form[:100]))
        super().__init__(
            placeholder=f"Select active form for {contender_label}...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=custom_id,
        )


class FormSelectionView(discord.ui.View):
    def __init__(
        self,
        contender_a: str,
        contender_b: str,
        forms_a: list[str],
        forms_b: list[str],
        *,
        on_confirmed: Any,
        timeout: float = 45.0,
    ):
        super().__init__(timeout=timeout)
        self.contender_a = contender_a
        self.contender_b = contender_b
        self.selected_form_a: str | None = None
        self.selected_form_b: str | None = None
        self.on_confirmed = on_confirmed

        if forms_a:
            self.select_a = FormSelectionDropdown(contender_a, forms_a, "select_form_a")
            async def cb_a(interaction: discord.Interaction):
                self.selected_form_a = self.select_a.values[0] if self.select_a.values[0] != "base" else None
                await interaction.response.defer()
            self.select_a.callback = cb_a
            self.add_item(self.select_a)

        if forms_b:
            self.select_b = FormSelectionDropdown(contender_b, forms_b, "select_form_b")
            async def cb_b(interaction: discord.Interaction):
                self.selected_form_b = self.select_b.values[0] if self.select_b.values[0] != "base" else None
                await interaction.response.defer()
            self.select_b.callback = cb_b
            self.add_item(self.select_b)

        confirm_btn = discord.ui.Button(label="Confirm Form & Fight!", style=discord.ButtonStyle.primary, row=2)
        async def confirm_callback(interaction: discord.Interaction):
            self.stop()
            await self.on_confirmed(interaction, self.selected_form_a, self.selected_form_b)
        confirm_btn.callback = confirm_callback
        self.add_item(confirm_btn)



def fight_response_ephemeral(private: bool = False) -> bool:
    return bool(private)


def missing_fighter_slug(query: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", query.casefold()).strip("-")
    return slug or "unknown"


async def enqueue_missing_fighter(connection: Any, query: str) -> bool:
    slug = missing_fighter_slug(query)
    return await enqueue_job(
        connection,
        profile_path=f"profiles/needs_review/mixed/user-requests/{slug}.yaml",
        target=query,
        providers="vsbattles,character_stats_profiles,superherodb",
        priority=25,
        max_attempts=3,
    )


async def discord_message_from_packet(
    packet: dict[str, Any],
    smoke_result: dict[str, Any],
    *,
    connection: Any | None = None,
    include_diagnostics: bool = False,
) -> str:
    if packet.get("errors"):
        lines = [smoke_result["label"], "Character not battle-ready yet."]
        for error in packet["errors"]:
            lines.append(f"- {error['contender']}: {error['status']} for {error['query']!r}")
            if error.get("alias_match"):
                lines.append(f"  alias matched: {error['alias_match']['canonical']}")
            if error.get("canonical_not_battle_ready"):
                lines.append("  matched character is not battle-ready yet")
            diagnostics = error.get("diagnostics") or {}
            if include_diagnostics:
                for path in (diagnostics.get("generated_paths") or [])[:3]:
                    lines.append(f"  generated: {path}")
                for path in (diagnostics.get("needs_review_paths") or [])[:3]:
                    lines.append(f"  needs_review: {path}")
            if connection is not None:
                suggestions = await search_characters(error["query"], connection=connection, limit=3)
                if suggestions:
                    lines.append("  suggestions:")
                    lines.extend(f"    {line}" for line in format_search_results(suggestions).splitlines())
                inserted = await enqueue_missing_fighter(connection, str(error["query"]))
                if inserted:
                    lines.append("  queued for retrieval")
                else:
                    lines.append("  already queued or awaiting review")
        lines.append('Try /search query:"<name>". Missing fighters are queued automatically.')
        text = "\n".join(lines)
    else:
        decision = await judge_fight_packet(packet, smoke_result)
        text = format_decision(decision, include_diagnostics=include_diagnostics)
    if len(text) <= 1800:
        return text
    return clamp_text(text, 1800)


def build_confidence_embed_color(confidence: str) -> discord.Color:
    normalized = str(confidence or "").casefold()
    if normalized in {"strong", "high"}:
        return discord.Color(0x10B981)
    if "medium" in normalized:
        return discord.Color(0xF59E0B)
    if "low" in normalized or "close" in normalized:
        return discord.Color(0xF97316)
    if "upset" in normalized or "uncertain" in normalized:
        return discord.Color(0xD946EF)
    return discord.Color(0x64748B)


def title_case_confidence(confidence: str) -> str:
    return str(confidence or "unknown").replace("_", " ").title()


def fighter_card_value(card: dict[str, Any]) -> str:
    tools = card.get("key_tools") or ["No named tools supplied."]
    lines = []
    if card.get("height_weight"):
        lines.append(f"Height/Weight: {card['height_weight']}")
    if card.get("weapon_power"):
        lines.append(f"Weapon/Power: {' • '.join(str(tool) for tool in card['weapon_power'][:2])}")
    if card.get("style"):
        lines.append(f"Style: {card['style']}")
    lines.extend(
        [
            f"Key tools: {' • '.join(str(tool) for tool in tools[:3])}",
            f"Win path: {card.get('win_path') or 'Needs a clearer packet-backed win route.'}",
            f"Risk: {card.get('risk') or 'No clean exploitable weakness supplied.'}",
        ]
    )
    return compact_field(
        "\n".join(lines[:5]),
        900,
    )


async def send_ephemeral_chunks(interaction: discord.Interaction, title: str, content: str) -> None:
    chunks = split_text_for_discord(content or "No detail available.", 1800)
    for index, chunk in enumerate(chunks):
        prefix = f"**{title} - Page {index + 1}/{len(chunks)}**\n"
        if index == 0:
            await interaction.response.send_message(prefix + chunk, ephemeral=True)
        else:
            await interaction.followup.send(prefix + chunk, ephemeral=True)


SECTION_TITLES = {
    "quick_evidence": "Quick Evidence", "quick_verdict": "Quick Verdict",
    "full_battle": "Multi-Stage Play-by-Play", "stats": "Stat Matrix & Feat Comparison",
    "equipment": "Equipment & Tool Loadout", "decisive": "Decisive Factor & Hax Breakdown",
    "phase_0": "Neutral & Probing Exchange", "phase_1": "Escalation & Tool Deployment",
    "phase_2": "Climax & Finishing Blow", "sources": "Sources", "details": "Details",
}


class FightDetailsView(discord.ui.View):
    """The public fight card exposes just the four entry points."""
    def __init__(self, details: dict[str, str], *, timeout: float = 900, private: bool = False) -> None:
        super().__init__(timeout=timeout)
        self.details = details
        self.private = private
        for key, label in (("quick_evidence", "Quick Evidence"), ("quick_verdict", "Quick Verdict"),
                           ("full_battle", "Full Battle Breakdown"), ("details", "Details")):
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary)
            async def open_section(interaction, section=key):
                view = FightPanelView(self.details, section)
                if self.private:
                    await interaction.response.edit_message(content=view.content(), embed=None, view=view)
                else:
                    await interaction.response.send_message(view.content(), view=view, ephemeral=True)
            button.callback = open_section
            self.add_item(button)
        self.add_item(
            discord.ui.Button(
                label="Open Web Battle Arena",
                url="https://altprox.tail4e8997.ts.net/",
                style=discord.ButtonStyle.link,
                emoji="🌐",
            )
        )



class FightPanelView(discord.ui.View):
    def __init__(self, details, section, *, page=0):
        super().__init__(timeout=900)
        self.details, self.section, self.page = details, section, page
        text = details.get(section, "Choose a detail section below.")
        self.pages = split_text_for_discord(text, 1700)
        if section in {"full_battle", "phase_0", "phase_1", "phase_2"}:
            options = [discord.SelectOption(label=SECTION_TITLES[k], value=k)
                       for k in ("full_battle", "phase_0", "phase_1", "phase_2")]
            select = discord.ui.Select(placeholder="Full battle or one phase", options=options, row=0)
            select.callback = self.choose
            self.add_item(select)
        elif section in {"details", "stats", "equipment", "decisive"}:
            select = discord.ui.Select(placeholder="Choose supporting detail", options=[
                discord.SelectOption(label=SECTION_TITLES[k], value=k) for k in ("stats", "equipment", "decisive")], row=0)
            select.callback = self.choose
            self.add_item(select)
        for label, target in (("Back to fight options", "home"), ("Sources", "sources")):
            if target == section:
                continue
            button = discord.ui.Button(label=label, row=1)
            async def navigate(interaction, key=target):
                if key == "home":
                    await interaction.response.edit_message(content="**Choose a fight section**", embed=None,
                                                           view=FightDetailsView(self.details, private=True))
                else:
                    await self.show(interaction, key)
            button.callback = navigate
            self.add_item(button)
        if len(self.pages) > 1:
            for label, delta in (("Previous", -1), ("Next", 1)):
                button = discord.ui.Button(label=label, row=2, disabled=not 0 <= self.page + delta < len(self.pages))
                async def paginate(interaction, step=delta):
                    await self.show(interaction, self.section, self.page + step)
                button.callback = paginate
                self.add_item(button)

    def content(self):
        return f"**{SECTION_TITLES[self.section]}** — {self.page + 1}/{len(self.pages)}\n{self.pages[self.page]}"

    async def choose(self, interaction):
        key = interaction.data.get("values", [""])[0]
        allowed = {option.value for child in self.children if isinstance(child, discord.ui.Select) for option in child.options}
        if key not in allowed:
            await interaction.response.send_message("That section is unavailable.", ephemeral=True)
            return
        await self.show(interaction, key)

    async def show(self, interaction, key, page=0):
        view = FightPanelView(self.details, key, page=page)
        await interaction.response.edit_message(content=view.content(), embed=None, view=view)


def fight_detail_payload(decision: dict[str, Any]) -> dict[str, str]:
    structured = structured_decision_output(decision)
    packet = decision.get("presentation_packet") or {}
    content = personality_details(decision, packet)
    winner = decision.get("winner") or "Unresolved"
    difficulty = decision.get("difficulty") or "Unresolved"
    verdict = decision.get("quick_verdict") or "A matchup-specific verdict is not available yet. Review the evidence before relying on the provisional result."
    return {
        **{key: linked_citations(value, packet) for key, value in content.items()},
        "quick_verdict": f"**Predicted winner: {winner}**\n**Difficulty: {difficulty}**\n\n" + linked_citations(verdict, packet),
        "quick_evidence": evidence_brief(packet),
        "full_battle": linked_citations("\n\n".join(content[f"phase_{i}"] for i in range(3)), packet),
        "sources": source_panel(packet),
        "full_analysis": structured["full_analysis"],
        "full_evidence": structured["full_evidence"] or "No expanded evidence available.",
        "loser_best_path": structured["loser_best_path_full"] or "No alternate loser path available.",
    }


def build_fight_embed(decision: dict[str, Any], *, status: str | None = None) -> tuple[discord.Embed, str]:
    structured = structured_decision_output(decision)
    packet = decision.get("presentation_packet") or {}
    embed = discord.Embed(title=structured["display_title"],
                          url="https://altprox.tail4e8997.ts.net/",
                          description=status or "Choose Quick Evidence, Quick Verdict, or Full Battle Breakdown below.",
                          color=discord.Color(0x5865F2))
    for index, side in enumerate(("contender_a", "contender_b")):
        contender = packet.get(side) or {}
        cards = structured["fighter_cards"]
        card = cards[index] if index < len(cards) else {}
        name = contender.get("canonical_name") or card.get("fighter_name") or "Fighter"
        variant = contender.get("variant") or {}
        version = variant.get("variant_name") or variant.get("label") or variant.get("name") or variant.get("form") or "Canonical base; no additional form selected"
        raw_abilities = [
            sanitize_fight_card_item(str(x.get("name") or ""))
            for x in contender.get("abilities", [])
        ]
        raw_equipment = [
            sanitize_fight_card_item(str(x.get("name") or ""))
            for x in contender.get("equipment", [])
        ]
        raw_card_tools = [
            sanitize_fight_card_item(str(x or ""))
            for x in (card.get("key_tools") or [])
        ]
        all_candidates: list[str] = []
        for x in raw_abilities + raw_card_tools:
            if x and x not in all_candidates and not is_dirty_fight_card_item(x) and not re.search(r"(?i)border|scroll\s*=|visible\s*=|padding\s*=|content\s*=|\{\{|tabber", x):
                all_candidates.append(x)

        def _is_generic(s: str) -> bool:
            sf = s.casefold()
            return any(sf.startswith(p) for p in ("superhuman physical", "superhuman characteristics", "peak human", "enhanced human"))

        specific = [x for x in all_candidates if not _is_generic(x)]
        generic = [x for x in all_candidates if _is_generic(x)]
        tools = (specific + generic)[:4]

        clean_gear = [
            x for x in raw_equipment
            if x and not is_dirty_fight_card_item(x) and not re.search(r"(?i)border|scroll\s*=|visible\s*=|padding\s*=|content\s*=|\{\{|tabber", x)
        ][:3]

        lines = [f"Version/form: {version}"]
        lines.append("Signature tools: " + (", ".join(tools) or "Not established by supplied evidence"))
        if clean_gear:
            lines.append("Equipment: " + ", ".join(clean_gear))
        value = "\n".join(lines)
        embed.add_field(name=f"{'🟥' if index == 0 else '🟦'} {name} — Fight Card", value=compact_field(value, 900), inline=False)
    rules = packet.get("rules") or {}
    conditions = "Standard encounter • standard equipment • no prep unless explicitly granted • no energy equalization"
    if rules.get("energy_equalization"):
        conditions = "Standard encounter • energy equalization enabled for this matchup"
    embed.add_field(name="Battle conditions", value=conditions, inline=False)
    embed.set_footer(text="Nerd Fight Referee • evidence-backed matchup analysis")
    return embed, structured["full_analysis"]


async def send_deferred_fight_result(
    interaction: discord.Interaction,
    packet: dict[str, Any],
    smoke_result: dict[str, Any],
    *,
    ephemeral: bool,
) -> str:
    smoke_result["presentation_packet"] = packet
    initial_embed, _ = build_fight_embed(smoke_result, status="Generating full referee breakdown...")
    initial_view = FightDetailsView(fight_detail_payload(smoke_result))
    message = await interaction.followup.send(embed=initial_embed, view=initial_view, ephemeral=ephemeral, wait=True)
    decision = await judge_fight_packet(packet, smoke_result)
    decision["presentation_packet"] = packet
    text = format_decision(decision, include_diagnostics=ephemeral)
    structured = structured_decision_output(decision)
    status = "Choose a section below to explore the matchup."
    if (decision.get("diagnostics") or {}).get("fallback") and (decision.get("diagnostics") or {}).get("fallback_reason") != "llm_explanation":
        status = "Full breakdown unavailable. The evidence and provisional assessment remain available."
    final_embed, _ = build_fight_embed(decision, status=status)
    final_view = FightDetailsView(fight_detail_payload(decision))
    try:
        await message.edit(embed=final_embed, view=final_view)
    except Exception:  # noqa: BLE001 - fallback to a follow-up if webhook edit is unavailable.
        await interaction.followup.send(embed=final_embed, view=final_view, ephemeral=ephemeral)
    return text


def register_fight_command(tree: app_commands.CommandTree, *, database_url: str | None = None) -> None:
    @tree.command(name="fight", description="Run a Nerd Fight Referee matchup with optional form selection")
    @app_commands.describe(
        contender_a="First character name or alias (e.g. Goku, Flash, Superman)",
        contender_b="Second character name or alias (e.g. Hulk, Vegeta, Thor)",
        form_a="Optional active form/era for contender A (or pick via dropdown)",
        form_b="Optional active form/era for contender B (or pick via dropdown)",
        private="Only show the fight breakdown to you",
    )
    async def fight(
        interaction: discord.Interaction,
        contender_a: str,
        contender_b: str,
        form_a: str | None = None,
        form_b: str | None = None,
        private: bool = False,
    ) -> None:
        ephemeral = fight_response_ephemeral(private)

        target_a = f"{contender_a} ({form_a})" if form_a and f"({form_a})" not in contender_a else contender_a
        target_b = f"{contender_b} ({form_b})" if form_b and f"({form_b})" not in contender_b else contender_b

        forms_a = available_forms_for_query(contender_a) if not form_a and "(" not in contender_a else []
        forms_b = available_forms_for_query(contender_b) if not form_b and "(" not in contender_b else []

        async def execute_fight(inter: discord.Interaction, picked_a: str | None, picked_b: str | None) -> str:
            resolved_a = f"{contender_a} ({picked_a})" if picked_a else target_a
            resolved_b = f"{contender_b} ({picked_b})" if picked_b else target_b

            if not inter.response.is_done():
                await inter.response.defer(thinking=True, ephemeral=ephemeral)

            async with connect_database(database_url) as connection:
                packet = await build_fight_packet(
                    connection,
                    resolved_a,
                    resolved_b,
                    rules={
                        "smoke": True,
                        "llm_enabled": os.getenv("BATTLEBOT_LLM_ENABLED", "").lower() in {"1", "true", "yes", "on"},
                        "llm_model": os.getenv("BATTLEBOT_LLM_MODEL") or "",
                    },
                )
                smoke_result = smoke_judge_packet(packet)
                if packet.get("errors"):
                    text = await discord_message_from_packet(
                        packet,
                        smoke_result,
                        connection=connection,
                        include_diagnostics=ephemeral,
                    )
                    await inter.followup.send(text, ephemeral=ephemeral)
                    return text
                return await send_deferred_fight_result(inter, packet, smoke_result, ephemeral=ephemeral)

        async def handler() -> str:
            if (forms_a or forms_b) and not form_a and not form_b:
                embed = discord.Embed(
                    title="Form Selection Available",
                    description=f"Multiple canonical forms exist for this matchup.\nChoose specific active forms below, or click **Confirm Form & Fight** to proceed with base/strongest canonical forms.",
                    color=discord.Color(0xF1C40F),
                )
                view = FormSelectionView(contender_a, contender_b, forms_a, forms_b, on_confirmed=execute_fight)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
                return "Prompted for form selection"

            return await execute_fight(interaction, None, None)

        await run_audited_command(
            interaction,
            command_name="fight",
            options={"contender_a": target_a, "contender_b": target_b, "form_a": form_a, "form_b": form_b, "private": private},
            response_is_private=ephemeral,
            database_url=database_url,
            handler=handler,
        )

    async def character_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        needle = current.strip().casefold()
        choices: list[app_commands.Choice[str]] = []
        seen = set()

        if needle:
            for seed in CURATED_VARIANTS:
                display = f"{seed.parent_name} ({seed.variant_name})"
                if (
                    needle in display.casefold()
                    or needle in seed.parent_name.casefold()
                    or any(needle in a.casefold() for a in seed.aliases.split("|") if a)
                ):
                    if display.casefold() not in seen:
                        seen.add(display.casefold())
                        choices.append(app_commands.Choice(name=display[:100], value=display[:100]))
                if len(choices) >= 12:
                    break

        try:
            async with connect_database(database_url) as connection:
                rows = await search_characters(current or "a", connection=connection, limit=12)
                for row in rows:
                    name = row.get("canonical_name") or ""
                    if name and name.casefold() not in seen:
                        seen.add(name.casefold())
                        choices.append(app_commands.Choice(name=name[:100], value=name[:100]))
                    if len(choices) >= 25:
                        break
        except Exception:
            pass

        return choices[:25]

    async def form_a_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        contender_a_val = str(getattr(interaction.namespace, "contender_a", "") or "")
        forms = available_forms_for_query(contender_a_val)
        needle = current.strip().casefold()
        return [
            app_commands.Choice(name=f[:100], value=f[:100])
            for f in forms
            if not needle or needle in f.casefold()
        ][:25]

    async def form_b_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        contender_b_val = str(getattr(interaction.namespace, "contender_b", "") or "")
        forms = available_forms_for_query(contender_b_val)
        needle = current.strip().casefold()
        return [
            app_commands.Choice(name=f[:100], value=f[:100])
            for f in forms
            if not needle or needle in f.casefold()
        ][:25]

    fight.autocomplete("contender_a")(character_autocomplete)
    fight.autocomplete("contender_b")(character_autocomplete)
    fight.autocomplete("form_a")(form_a_autocomplete)
    fight.autocomplete("form_b")(form_b_autocomplete)

