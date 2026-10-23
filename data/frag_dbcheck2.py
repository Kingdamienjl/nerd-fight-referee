#!/usr/bin/env python3
"""Where do promoted profiles live in character_profiles? Key format check."""
import asyncio
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.common.db import connect_database


async def main():
    async with connect_database() as conn:
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'character_profiles' ORDER BY ordinal_position")
        print("columns:", [c["column_name"] for c in cols])
        rows = await conn.fetch(
            "SELECT * FROM character_profiles WHERE profile_path ILIKE '%deathstroke%'")
        for r in rows:
            d = dict(r)
            print({k: d[k] for k in ("profile_path", "name") if k in d})
        sample = await conn.fetch(
            "SELECT profile_path FROM character_profiles ORDER BY profile_path LIMIT 3")
        for r in sample:
            print("keyformat:", r["profile_path"])


asyncio.run(main())
