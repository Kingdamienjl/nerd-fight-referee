"""Discord bot entrypoint with multi-guild support and instant slash command sync."""

from __future__ import annotations

import os
import logging

import discord
from discord import app_commands

from battlebot.bot.commands.catalog import register_catalog_commands
from battlebot.bot.commands.fight import register_fight_command
from battlebot.common.db import apply_schema, connect_database


BOT_PUBLIC_NAME = "Nerd Fight Referee"
LOGGER = logging.getLogger(__name__)
EXPECTED_COMMANDS = ("fight", "search", "characters", "profile", "needs_review", "repair_queue")


def command_names(tree: app_commands.CommandTree) -> list[str]:
    return sorted(command.name for command in tree.get_commands())


def startup_environment_summary() -> dict[str, str]:
    return {
        "DATABASE_URL": "yes" if os.getenv("DATABASE_URL") else "no",
        "DISCORD_GUILD_ID": os.getenv("DISCORD_GUILD_ID") or "",
        "BATTLEBOT_LLM_ENABLED": os.getenv("BATTLEBOT_LLM_ENABLED") or "",
        "BATTLEBOT_LLM_MODEL": os.getenv("BATTLEBOT_LLM_MODEL") or "",
    }


class BattleBotClient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        register_fight_command(self.tree, database_url=os.getenv("DATABASE_URL"))
        register_catalog_commands(self.tree, database_url=os.getenv("DATABASE_URL"))

    async def setup_hook(self) -> None:
        LOGGER.info("Startup environment: %s", startup_environment_summary())
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            try:
                async with connect_database(database_url) as connection:
                    await apply_schema(connection)
            except Exception as exc:  # noqa: BLE001 - audit schema creation must not block Discord startup.
                LOGGER.warning("Database schema setup failed; audit JSONL fallback remains available: %s", exc)
        LOGGER.info("Local command names before sync: %s", ", ".join(command_names(self.tree)))

        # 1. Global sync so all servers receive slash commands
        try:
            global_synced = await self.tree.sync()
            LOGGER.info("Discord accepted %d global command(s): %s", len(global_synced), ", ".join(sorted(c.name for c in global_synced)))
        except Exception as exc:
            LOGGER.error("Discord global tree sync failed: %s", exc)

        # 2. Specific guild sync if requested for zero-delay test deployment
        guild_sync_id = os.getenv("DISCORD_GUILD_ID")
        if guild_sync_id:
            try:
                guild = discord.Object(id=int(guild_sync_id))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                LOGGER.info("Discord accepted guild command names: %s", ", ".join(sorted(command.name for command in synced)))
            except Exception as exc:
                LOGGER.warning("Failed to sync to specific guild %s: %s", guild_sync_id, exc)

    async def on_ready(self) -> None:
        LOGGER.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else "unknown")
        LOGGER.info("Connected to %d guild(s):", len(self.guilds))
        for guild in self.guilds:
            LOGGER.info(" - %s (ID: %s, members: %d)", guild.name, guild.id, guild.member_count)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        LOGGER.info("Joined new guild: %s (ID: %s, members: %d). Syncing commands...", guild.name, guild.id, guild.member_count)
        try:
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            LOGGER.info("Successfully synced %d commands to new guild: %s", len(synced), guild.name)
        except Exception as exc:
            LOGGER.error("Failed to sync commands to new guild %s: %s", guild.name, exc)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        LOGGER.info("Removed from guild: %s (ID: %s)", guild.name, guild.id)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN is not set; bot not started")
        return
    BattleBotClient().run(token)


if __name__ == "__main__":
    main()
