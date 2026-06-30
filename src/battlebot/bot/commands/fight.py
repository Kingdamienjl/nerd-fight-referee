"""Pre-LLM /fight smoke slash command."""

from __future__ import annotations

import re
from typing import Any

import os

import discord
from discord import app_commands

from battlebot.bot.audit import run_audited_command
from battlebot.common.db import connect_database
from battlebot.fight.decision_formatter import clamp_text, compact_field, format_decision, split_text_for_discord, structured_decision_output
from battlebot.fight.llm_judge import judge_fight_packet
from battlebot.fight.smoke_judge import smoke_judge_packet
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.profiles.search import format_search_results, search_characters
from battlebot.review.queue import enqueue_job


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
    return compact_field(
        "\n".join(
            [
                f"Tools: {' • '.join(str(tool) for tool in tools[:4])}",
                f"Win path: {card.get('win_path') or 'Needs a clearer packet-backed win route.'}",
                f"Risk: {card.get('risk') or 'No clean exploitable weakness supplied.'}",
            ]
        ),
        900,
    )


async def send_ephemeral_chunks(interaction: discord.Interaction, title: str, content: str) -> None:
    chunks = split_text_for_discord(content or "No detail available.", 1800)
    for index, chunk in enumerate(chunks):
        prefix = f"**{title}**\n" if index == 0 else f"**{title} continued**\n"
        if index == 0:
            await interaction.response.send_message(prefix + chunk, ephemeral=True)
        else:
            await interaction.followup.send(prefix + chunk, ephemeral=True)


class FightDetailsView(discord.ui.View):
    def __init__(self, details: dict[str, str], *, timeout: float = 900) -> None:
        super().__init__(timeout=timeout)
        self.details = details

    @discord.ui.button(label="🧠 Full Analysis", style=discord.ButtonStyle.primary)
    async def full_analysis(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        await send_ephemeral_chunks(interaction, "Full Analysis", self.details.get("full_analysis") or "")

    @discord.ui.button(label="📜 Evidence", style=discord.ButtonStyle.secondary)
    async def evidence(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        await send_ephemeral_chunks(interaction, "Evidence", self.details.get("full_evidence") or "")

    @discord.ui.button(label="🛣️ Loser's Path", style=discord.ButtonStyle.secondary)
    async def loser_path(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # noqa: ARG002
        await send_ephemeral_chunks(interaction, "Loser's Path", self.details.get("loser_best_path") or "")


def fight_detail_payload(decision: dict[str, Any]) -> dict[str, str]:
    structured = structured_decision_output(decision)
    return {
        "full_analysis": structured["full_analysis"],
        "full_evidence": structured["full_evidence"] or "No expanded evidence available.",
        "loser_best_path": structured["loser_best_path"] or "No alternate loser path available.",
    }


def build_fight_embed(decision: dict[str, Any], *, status: str | None = None) -> tuple[discord.Embed, str]:
    structured = structured_decision_output(decision)
    confidence = structured["confidence"] or "unknown"
    status_text = status or structured["status"] or structured["short_summary"]
    status_icon = "⚠️" if str(status_text).startswith("⚠️") else "⏳" if status else "🧾"
    embed = discord.Embed(
        title=structured["display_title"],
        description=(
            f"🏆 Winner: {structured['winner'] or 'pending'}\n"
            f"📊 Battle odds: {structured['battle_odds_text']}\n"
            f"🎚️ Confidence: {title_case_confidence(confidence)}\n"
            f"{status_icon} Referee status: {compact_field(status_text.removeprefix('⚠️').strip(), 220)}"
        ),
        color=build_confidence_embed_color(confidence),
    )
    for index, card in enumerate(structured["fighter_cards"][:2]):
        badge = "🟥" if index == 0 else "🟦"
        embed.add_field(
            name=f"{badge} {card['fighter_name']} — Fight Card",
            value=fighter_card_value(card),
            inline=False,
        )
    embed.add_field(
        name="⚖️ Quick Verdict",
        value=compact_field(structured["quick_verdict"], 900),
        inline=False,
    )
    if structured["quick_evidence"]:
        embed.add_field(
            name="🔎 Quick Evidence",
            value=compact_field("\n".join(f"• {bullet}" for bullet in structured["quick_evidence"][:3]), 900),
            inline=False,
        )
    embed.set_footer(text="Nerd Fight Referee • deterministic verdict, LLM commentary")
    return embed, structured["full_analysis"]


async def send_deferred_fight_result(
    interaction: discord.Interaction,
    packet: dict[str, Any],
    smoke_result: dict[str, Any],
    *,
    ephemeral: bool,
) -> str:
    initial_embed, _ = build_fight_embed(smoke_result, status="Generating full referee breakdown...")
    initial_view = FightDetailsView(fight_detail_payload(smoke_result))
    message = await interaction.followup.send(embed=initial_embed, view=initial_view, ephemeral=ephemeral, wait=True)
    decision = await judge_fight_packet(packet, smoke_result)
    text = format_decision(decision, include_diagnostics=ephemeral)
    structured = structured_decision_output(decision)
    status = structured["short_summary"]
    if (decision.get("diagnostics") or {}).get("fallback") and (decision.get("diagnostics") or {}).get("fallback_reason") != "llm_explanation":
        status = "⚠️ Full breakdown unavailable; deterministic verdict remains."
    final_embed, _ = build_fight_embed(decision, status=status)
    final_view = FightDetailsView(fight_detail_payload(decision))
    try:
        await message.edit(embed=final_embed, view=final_view)
    except Exception:  # noqa: BLE001 - fallback to a follow-up if webhook edit is unavailable.
        await interaction.followup.send(embed=final_embed, view=final_view, ephemeral=ephemeral)
    return text


def register_fight_command(tree: app_commands.CommandTree, *, database_url: str | None = None) -> None:
    @tree.command(name="fight", description="Run a Nerd Fight Referee matchup")
    @app_commands.describe(
        contender_a="First character name or alias",
        contender_b="Second character name or alias",
    )
    async def fight(
        interaction: discord.Interaction,
        contender_a: str,
        contender_b: str,
        private: bool = False,
    ) -> None:
        ephemeral = fight_response_ephemeral(private)

        async def handler() -> str:
            await interaction.response.defer(thinking=True, ephemeral=ephemeral)
            async with connect_database(database_url) as connection:
                packet = await build_fight_packet(
                    connection,
                    contender_a,
                    contender_b,
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
                    await interaction.followup.send(text, ephemeral=ephemeral)
                    return text
                return await send_deferred_fight_result(interaction, packet, smoke_result, ephemeral=ephemeral)

        await run_audited_command(
            interaction,
            command_name="fight",
            options={"contender_a": contender_a, "contender_b": contender_b, "private": private},
            response_is_private=ephemeral,
            database_url=database_url,
            handler=handler,
        )
