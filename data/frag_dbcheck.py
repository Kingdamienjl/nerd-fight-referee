#!/usr/bin/env python3
"""Check the two sample-50e promotions landed in the DB; runner liveness."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.common.db import connect_database

PATHS = [
    "profiles/needs_review/comic/dc/deathstroke-dc-comics.yaml",
    "profiles/needs_review/comic/dc/deathstroke-post-crisis.yaml",
]


async def main():
    async with connect_database() as conn:
        total = await conn.fetchval("SELECT count(*) FROM character_profiles")
        print("battle_eligible_total:", total)
        for p in PATHS:
            rows = await conn.fetch(
                "SELECT profile_path FROM character_profiles WHERE profile_path = $1", p)
            gen = Path(str(p).replace("profiles/needs_review/", "profiles/generated/"))
            print(p, "db_rows:", len(rows), "generated_yaml_exists:", gen.exists())
        jobs = await conn.fetch(
            "SELECT profile_path, status FROM profile_jobs "
            "WHERE profile_path = ANY($1)", PATHS)
        for j in jobs:
            print("job:", j["profile_path"], j["status"])


asyncio.run(main())

alive = []
for proc in Path("/proc").glob("[0-9]*/cmdline"):
    try:
        if "recovery_run" in proc.read_text(errors="ignore"):
            alive.append(proc.parent.name)
    except Exception:
        pass
print("recovery_run_pids:", alive)
