#!/usr/bin/env python3
"""Frag-3 Part-1 post-clean verification: re-import generated
(refreshes DB rows), fresh battle_eligible count, and check the 8
cleaned profiles' DB rows directly for any surviving template
artifacts (item names + the rimuru AP entry)."""
import asyncio
import json
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.common.db import connect_database, database_url
from battlebot.review import queue_worker, service

TARGETS = (
    "profiles/generated/anime/demon-slayer/shinobu-kocho.yaml",
    "profiles/generated/anime/dragon-ball/beerus-game.yaml",
    "profiles/generated/anime/dragon-ball/cell-classic.yaml",
    "profiles/generated/anime/dragon-ball/future-trunks-anime.yaml",
    "profiles/generated/anime/dragon-ball/trunks-anime.yaml",
    "profiles/generated/anime/dragon-ball/vegeta-classic.yaml",
    "profiles/generated/anime/that-time-i-got-reincarnated-as-a-slime/rimuru-tempest.yaml",
)
BAD = (
    "self-explanatory feats",
    "speed feats",
    "durability feats",
    "will finish upon return",
    "attacks/abilities can cover",
    "attack power or destructive capacity (in bold",
)


async def main():
    imported = await queue_worker.import_generated_profiles(
        service.DEFAULT_GENERATED_DIR, database_url=database_url()
    )
    print("imported:", imported)
    async with connect_database() as conn:
        total = await conn.fetchval("SELECT count(*) FROM character_profiles")
        print("battle_eligible_after_clean:", total)
        for rel in TARGETS:
            row = await conn.fetchrow(
                "SELECT profile_json FROM character_profiles "
                "WHERE profile_path = $1",
                rel,
            )
            if row is None:
                print(f"{rel} DB row: MISSING")
                continue
            payload = row["profile_json"]
            prof = json.loads(payload) if isinstance(payload, str) else payload
            blob = json.dumps(prof).casefold()
            hits = [b for b in BAD if b in blob]
            weaknesses = [
                str(i.get("name"))[:60]
                for i in (prof.get("weaknesses") or [])
                if isinstance(i, dict)
            ]
            ap = ((prof.get("power_scale") or {}).get("attack_potency") or {})
            print(
                f"{rel} bad_hits={hits} ap_present={'attack_potency' in (prof.get('power_scale') or {})} "
                f"ap_text={str(ap.get('text') or '')[:50]!r} weaknesses={len(weaknesses)}"
            )


asyncio.run(main())
