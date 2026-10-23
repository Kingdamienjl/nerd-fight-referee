#!/usr/bin/env python3
"""Part-2 post-clean verification: re-import generated (refreshes
DB rows), rescan generated item NAMES for the exact patterns,
list remaining name hits, fresh battle_eligible count, and check
the grodd/etrigan files' weakness items directly."""
import asyncio
import glob
import json
import re
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.common.db import connect_database, database_url
from battlebot.review import queue_worker, service

BARE_LABEL = re.compile(r"(?i)^\s*deviant\s?art\s*\d*\s*[.…]*\s*$")
BUNDLE_PREFIX = "please read and follow the Power-scaling Rules"


def load(path):
    with open(path) as handle:
        return yaml.load(handle, Loader=yaml.CSafeLoader) or {}


def iter_items(prof):
    for section in ("abilities", "weaknesses", "equipment"):
        items = prof.get(section)
        if isinstance(items, dict):
            items = list(items.values())
        for i in items or []:
            if isinstance(i, dict):
                yield section, i


remaining = []
for path in sorted(glob.glob("/app/profiles/generated/**/*.yaml", recursive=True)):
    try:
        prof = load(path)
    except Exception:  # noqa: BLE001
        continue
    rel = path.split("/app/")[-1]
    for section, item in iter_items(prof):
        name = str(item.get("name") or "")
        if (
            "Before making any changes" in name
            or BARE_LABEL.match(name)
            or name.startswith(BUNDLE_PREFIX)
        ):
            remaining.append(f"{rel} [{section}] {name[:100]!r}")
print(f"remaining_name_hits: {len(remaining)}")
for line in remaining:
    print("REMAINING:", line)

for rel in (
    "profiles/needs_review/comic/dc/gorilla-grodd.yaml",
    "profiles/needs_review/comic/dc/gorilla-grodd-dc-comics.yaml",
    "profiles/generated/comic/dc/gorilla-grodd-post-crisis.yaml",
):
    prof = load("/app/" + rel)
    names = [str(i.get("name"))[:80] for _s, i in iter_items(prof)
             if _s == "weaknesses"]
    print(f"{rel} weaknesses_now={names}")


async def main():
    imported = await queue_worker.import_generated_profiles(
        service.DEFAULT_GENERATED_DIR, database_url=database_url())
    print("imported:", imported)
    async with connect_database() as conn:
        total = await conn.fetchval("SELECT count(*) FROM character_profiles")
        print("battle_eligible_after:", total)
        for rel in (
            "profiles/generated/comic/dc/gorilla-grodd-post-crisis.yaml",
            "profiles/generated/comic/dc/circe-dc-comics.yaml",
            "profiles/generated/comic/dc/deathstroke-dc-comics.yaml",
        ):
            row = await conn.fetchrow(
                "SELECT profile_json FROM character_profiles "
                "WHERE profile_path = $1", rel)
            if row is None:
                print(f"{rel} DB row: MISSING")
                continue
            pj = row["profile_json"]
            text = pj if isinstance(pj, str) else json.dumps(pj)
            has_phrase = "Before making any changes" in text
            print(f"{rel} DB row present; phrase_in_json={has_phrase}")


asyncio.run(main())
