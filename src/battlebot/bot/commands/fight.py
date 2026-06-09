"""Non-LLM /fight debug slash command."""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands

from battlebot.common.db import connect_database
from battlebot.fight.debug import human_summary
from battlebot.profiles.fight_packet import build_fight_packet


def discord_message_from_packet(packet: dict[str, Any]) -> str:
    text = human_summary(packet)
    if len(text) <= 1900:
        return text
    return f"{text[:1897]}..."


def register_fight_command(tree: app_commands.CommandTree, *, database_url: str | None = None) -> None:
    @tree.command(name="fight", description="Build a non-LLM fight debug packet")
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
                rules={"debug": True, "llm_enabled": False},
            )
        await interaction.followup.send(discord_message_from_packet(packet))
