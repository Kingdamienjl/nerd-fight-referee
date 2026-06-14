"""Character catalog and review slash commands."""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands

from battlebot.common.db import connect_database
from battlebot.profiles.search import browse_character_catalog, format_character_catalog, format_search_results, search_characters
from battlebot.profiles.sheet import profile_sheet
from battlebot.review import service


REGISTERED_CATALOG_COMMANDS = ("search", "characters", "profile", "needs_review", "repair_queue")


def clamp_message(text: str, limit: int = 1900) -> str:
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def catalog_command_names() -> tuple[str, ...]:
    return REGISTERED_CATALOG_COMMANDS


def catalog_response_ephemeral(public: bool = False) -> bool:
    return not bool(public)


def is_admin_or_dm(interaction: discord.Interaction) -> bool:
    permissions = getattr(getattr(interaction, "user", None), "guild_permissions", None)
    return permissions is None or bool(getattr(permissions, "administrator", False))


def format_needs_review(profiles: list[dict[str, Any]]) -> str:
    if not profiles:
        return "No needs_review profiles found."
    lines = []
    for profile in profiles:
        reasons = ", ".join(profile.get("review_reasons") or []) or "needs review"
        lines.append(
            f"- {profile.get('name')} - {profile.get('franchise')}/{profile.get('category')} - {reasons}"
        )
    return clamp_message("\n".join(lines))


def format_repair_queue_command(category: str | None, franchise: str | None, limit: int, promote_if_valid: bool) -> str:
    parts = [
        ".venv/bin/python -m battlebot.review.batch_promote profiles/needs_review",
        f"--max-profiles {max(1, min(limit, 100))}",
        "--providers vsbattles,character_stats_profiles,superherodb,kaggle_superherodb",
        "--debug-dir data/repair_debug",
    ]
    if not promote_if_valid:
        parts.append("--dry-run")
    notes = []
    if category:
        notes.append(f"category filter requested: {category}")
    if franchise:
        notes.append(f"franchise filter requested: {franchise}")
    text = "Run this terminal command from the project root:\n`" + " ".join(parts) + "`"
    if notes:
        text += "\n" + "\n".join(notes)
    return text


async def sources_text(character: str, database_url: str | None) -> str:
    async with connect_database(database_url) as connection:
        sheet = await profile_sheet(character, connection=connection)
    lines = []
    in_sources = False
    for line in sheet.splitlines():
        if line == "Sources:":
            in_sources = True
            lines.append(line)
            continue
        if in_sources:
            lines.append(line)
    return clamp_message("\n".join(lines) if lines else "No sources found.")


def register_catalog_commands(tree: app_commands.CommandTree, *, database_url: str | None = None) -> None:
    @tree.command(name="search", description="Search imported, generated, review, and roster characters")
    async def search(interaction: discord.Interaction, query: str, limit: int = 10, public: bool = False) -> None:
        ephemeral = catalog_response_ephemeral(public)
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        async with connect_database(database_url) as connection:
            rows = await search_characters(query, connection=connection, limit=max(1, min(limit, 25)))
        await interaction.followup.send(clamp_message(format_search_results(rows)), ephemeral=ephemeral)

    @tree.command(name="characters", description="List available characters")
    async def characters(
        interaction: discord.Interaction,
        category: str | None = None,
        franchise: str | None = None,
        page: int = 1,
        limit: int = 20,
        public: bool = False,
    ) -> None:
        ephemeral = catalog_response_ephemeral(public)
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        async with connect_database(database_url) as connection:
            page_data = await browse_character_catalog(
                connection=connection,
                category=category,
                franchise=franchise,
                page=page,
                limit=limit,
            )
        await interaction.followup.send(clamp_message(format_character_catalog(page_data)), ephemeral=ephemeral)

    @tree.command(name="profile", description="Show a human-readable profile sheet")
    async def profile(interaction: discord.Interaction, character: str, public: bool = False) -> None:
        ephemeral = catalog_response_ephemeral(public)
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        async with connect_database(database_url) as connection:
            text = await profile_sheet(character, connection=connection)
        await interaction.followup.send(clamp_message(text), ephemeral=ephemeral)

    @tree.command(name="needs_review", description="List profiles waiting for review")
    async def needs_review(
        interaction: discord.Interaction,
        query: str | None = None,
        category: str | None = None,
        franchise: str | None = None,
        limit: int = 10,
    ) -> None:
        if not is_admin_or_dm(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        profiles = service.list_profiles(
            kind="needs_review",
            category=category,
            franchise=franchise,
            limit=max(1, min(limit, 50)),
        )
        if query:
            profiles = [profile for profile in profiles if query.casefold() in str(profile.get("name") or "").casefold()]
        await interaction.response.send_message(format_needs_review(profiles), ephemeral=True)

    @tree.command(name="repair_queue", description="Show a safe terminal command for review auto-repair")
    async def repair_queue(
        interaction: discord.Interaction,
        category: str | None = None,
        franchise: str | None = None,
        limit: int = 25,
        promote_if_valid: bool = True,
    ) -> None:
        if not is_admin_or_dm(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        await interaction.response.send_message(
            clamp_message(format_repair_queue_command(category, franchise, limit, promote_if_valid)),
            ephemeral=True,
        )
