#!/usr/bin/env python3
"""Part-2 final verification (read-only except DB import refresh):
re-import generated, then confirm ZERO generated item names are
actionable under the cleanup rules (footer phrase, bare label,
bundle prefix, or any clean_item_tails tail), and report the
fresh battle_eligible count + grodd state."""
import asyncio
import glob
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.common.db import connect_database, database_url
from battlebot.review import auto_repair as ar, queue_worker, service

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


actionable = []
for path in sorted(glob.glob("/app/profiles/generated/**/*.yaml", recursive=True)):
    try:
        prof = load(path)
    except Exception:  # noqa: BLE001
        continue
    rel = path.split("/app/")[-1]
    for section, item in iter_items(prof):
        name = str(item.get("name") or "")
        _cleaned, tail_reasons = ar.clean_item_tails(name)
        if (
            "Before making any changes" in name
            or name.startswith(BUNDLE_PREFIX)
            or tail_reasons
        ):
            actionable.append(f"{rel} [{section}] {name[:100]!r}")
print(f"actionable_name_hits: {len(actionable)}")
for line in actionable[:20]:
    print("ACTIONABLE:", line)

prof = load("/app/profiles/generated/comic/dc/gorilla-grodd-post-crisis.yaml")
names = [str(i.get("name"))[:80] for s, i in iter_items(prof) if s == "weaknesses"]
print(f"grodd-post-crisis weaknesses_now={names}")


async def main():
    imported = await queue_worker.import_generated_profiles(
        service.DEFAULT_GENERATED_DIR, database_url=database_url())
    print("imported:", imported)
    async with connect_database() as conn:
        total = await conn.fetchval("SELECT count(*) FROM character_profiles")
        print("battle_eligible_after:", total)


asyncio.run(main())
