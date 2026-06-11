"""Discord bot entrypoint."""

from __future__ import annotations

import os
import logging

import discord
from discord import app_commands

from battlebot.bot.commands.catalog import register_catalog_commands
from battlebot.bot.commands.fight import register_fight_command


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
        super().__init__(intents=discord.Intents.none())
        self.tree = app_commands.CommandTree(self)
        register_fight_command(self.tree, database_url=os.getenv("DATABASE_URL"))
        register_catalog_commands(self.tree, database_url=os.getenv("DATABASE_URL"))

    async def setup_hook(self) -> None:
        LOGGER.info("Startup environment: %s", startup_environment_summary())
        LOGGER.info("Local command names before sync: %s", ", ".join(command_names(self.tree)))
        guild_sync_id = os.getenv("DISCORD_GUILD_ID")
        if guild_sync_id:
            guild = discord.Object(id=int(guild_sync_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            LOGGER.info("Guild synced commands: %s", ", ".join(EXPECTED_COMMANDS))
            LOGGER.info("Discord accepted guild command names: %s", ", ".join(sorted(command.name for command in synced)))
        else:
            LOGGER.warning("DISCORD_GUILD_ID missing; global sync is being used and may not show immediately.")
            synced = await self.tree.sync()
            LOGGER.info("Discord accepted global command names: %s", ", ".join(sorted(command.name for command in synced)))


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN is not set; bot not started")
        return
    BattleBotClient().run(token)


if __name__ == "__main__":
    main()
