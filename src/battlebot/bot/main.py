"""Discord bot entrypoint."""

from __future__ import annotations

import os

import discord
from discord import app_commands

from battlebot.bot.commands.catalog import register_catalog_commands
from battlebot.bot.commands.fight import register_fight_command


BOT_PUBLIC_NAME = "Nerd Fight Referee"


class BattleBotClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.none())
        self.tree = app_commands.CommandTree(self)
        register_fight_command(self.tree, database_url=os.getenv("DATABASE_URL"))
        register_catalog_commands(self.tree, database_url=os.getenv("DATABASE_URL"))

    async def setup_hook(self) -> None:
        guild_sync_id = os.getenv("DISCORD_GUILD_SYNC_ID")
        if guild_sync_id:
            guild = discord.Object(id=int(guild_sync_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("DISCORD_TOKEN is not set; bot not started")
        return
    BattleBotClient().run(token)


if __name__ == "__main__":
    main()
