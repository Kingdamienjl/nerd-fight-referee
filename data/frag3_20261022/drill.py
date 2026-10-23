#!/usr/bin/env python3
"""Frag-3 verify drill-down: WHERE do the bad strings live in the
DB profile_json for beerus-game + rimuru? List weakness names from
DB vs file, and the JSON key paths containing the debris strings."""
import asyncio
import json
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.common.db import connect_database

TARGETS = (
    "profiles/generated/anime/dragon-ball/beerus-game.yaml",
    "profiles/generated/anime/that-time-i-got-reincarnated-as-a-slime/rimuru-tempest.yaml",
)
NEEDLES = ("self-explanatory feats", "speed feats", "will finish upon return")


def find_paths(obj, needle, prefix=""):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits += find_paths(v, needle, f"{prefix}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += find_paths(v, needle, f"{prefix}[{i}]")
    elif isinstance(obj, str) and needle in obj.casefold():
        hits.append(prefix)
    return hits


async def main():
    async with connect_database() as conn:
        for rel in TARGETS:
            row = await conn.fetchrow(
                "SELECT profile_json FROM character_profiles WHERE profile_path = $1",
                rel,
            )
            prof = json.loads(row["profile_json"])
            db_names = [
                str(i.get("name"))[:50]
                for i in (prof.get("weaknesses") or [])
                if isinstance(i, dict)
            ]
            with open("/app/" + rel) as handle:
                fprof = yaml.load(handle, Loader=yaml.CSafeLoader)
            file_names = [
                str(i.get("name"))[:50]
                for i in (fprof.get("weaknesses") or [])
                if isinstance(i, dict)
            ]
            print(f"== {rel}")
            print(f"   DB weaknesses ({len(db_names)}):", db_names[:8])
            print(f"   FILE weaknesses ({len(file_names)}):", file_names[:8])
            for needle in NEEDLES:
                paths = find_paths(prof, needle)
                if paths:
                    print(f"   DB needle {needle!r}: {paths[:6]}")
            ap = ((prof.get("power_scale") or {}).get("attack_potency") or {})
            print(f"   DB ap_text={str(ap.get('text') or '')[:60]!r}")
            fap = ((fprof.get("power_scale") or {}).get("attack_potency") or {})
            print(f"   FILE ap_text={str(fap.get('text') or '')[:60]!r}")


asyncio.run(main())
