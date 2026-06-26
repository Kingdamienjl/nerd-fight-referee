"""Pre-LLM /fight smoke slash command."""

from __future__ import annotations

import re
from typing import Any

import os

import discord
from discord import app_commands

from battlebot.common.db import connect_database
from battlebot.fight.decision_formatter import format_decision
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
    return f"{text[:1797]}..."


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
            text = await discord_message_from_packet(
                packet,
                smoke_judge_packet(packet),
                connection=connection,
                include_diagnostics=ephemeral,
            )
        await interaction.followup.send(text, ephemeral=ephemeral)
