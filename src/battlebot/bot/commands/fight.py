"""Pre-LLM /fight smoke slash command."""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands

from battlebot.common.db import connect_database
from battlebot.fight.smoke_judge import format_smoke_summary, smoke_judge_packet
from battlebot.profiles.fight_packet import build_fight_packet


def discord_message_from_packet(packet: dict[str, Any], smoke_result: dict[str, Any]) -> str:
    if packet.get("errors"):
        lines = [smoke_result["label"], "Resolution errors:"]
        for error in packet["errors"]:
            lines.append(f"- {error['contender']}: {error['status']} for {error['query']!r}")
            diagnostics = error.get("diagnostics") or {}
            for path in (diagnostics.get("generated_paths") or [])[:3]:
                lines.append(f"  generated: {path}")
            for path in (diagnostics.get("needs_review_paths") or [])[:3]:
                lines.append(f"  needs_review: {path}")
        text = "\n".join(lines)
    else:
        text = format_smoke_summary(smoke_result)
    if len(text) <= 1900:
        return text
    return f"{text[:1897]}..."


def register_fight_command(tree: app_commands.CommandTree, *, database_url: str | None = None) -> None:
    @tree.command(name="fight", description="Run a deterministic pre-LLM smoke fight")
    @app_commands.describe(
        contender_a="First character name or alias",
        contender_b="Second character name or alias",
    )
    async def fight(
        interaction: discord.Interaction,
        contender_a: str,
        contender_b: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        async with connect_database(database_url) as connection:
            packet = await build_fight_packet(
                connection,
                contender_a,
                contender_b,
                rules={"smoke": True, "llm_enabled": False},
            )
        await interaction.followup.send(discord_message_from_packet(packet, smoke_judge_packet(packet)))
