#!/usr/bin/env python3
"""Post-revert verification: re-import generated (refreshes etrigan's DB
row), confirm debris strings are gone from files + DB, list the cleaned
profiles' remaining weaknesses, fresh battle_eligible count."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.common.db import connect_database, database_url
from battlebot.review import queue_worker, service

CLEANED = {
    "profiles/generated/comic/dc/etrigan-dc-comics.yaml": None,
    "profiles/needs_review/comic/dc/gorilla-grodd-dc-comics.yaml": None,
    "profiles/needs_review/comic/dc/gorilla-grodd.yaml": None,
    "profiles/needs_review/comic/dc/deathstroke-rebirth.yaml": None,
    "profiles/needs_review/comic/dc/doctor-fate-rebirth.yaml": None,
}
DEBRIS = ("Before making any changes", "please read and follow",
          "Deviantart", "Often lashes out in rage Note:")

for rel in CLEANED:
    prof = yaml.load(open(rel), Loader=yaml.CSafeLoader) or {}
    items = prof.get("weaknesses")
    if isinstance(items, dict):
        items = list(items.values())
    names = [str(i.get("name"))[:60] for i in items or [] if isinstance(i, dict)]
    text = Path(rel).read_text()
    bad = [d for d in DEBRIS if d in text]
    print(f"{rel}\n  weaknesses_now={names}\n  debris_strings_in_file={bad}")


async def main():
    imported = await queue_worker.import_generated_profiles(
        service.DEFAULT_GENERATED_DIR, database_url=database_url())
    print("imported:", imported)
    async with connect_database() as conn:
        total = await conn.fetchval("SELECT count(*) FROM character_profiles")
        print("battle_eligible_after:", total)
        row = await conn.fetchrow(
            "SELECT profile_json FROM character_profiles WHERE profile_path = $1",
            "profiles/generated/comic/dc/etrigan-dc-comics.yaml")
        if row is None:
            print("etrigan DB row: MISSING")
        else:
            pj = row["profile_json"]
            text = pj if isinstance(pj, str) else json.dumps(pj)
            bad = [d for d in DEBRIS if d in text]
            print("etrigan DB row debris:", bad)


asyncio.run(main())
