"""Franchise intake runner (2026-10-25): verse categories -> dedupe -> roster CSVs.

Run inside referee-harvester-1, cwd /app:
  python data/franchise_intake_20261025.py --franchise "Hunter x Hunter" [--dry-run]
  python data/franchise_intake_20261025.py --all [--dry-run]

Writes profiles/rosters-staging/franchise_20261025_<slug>.csv (STAGING ONLY --
the harvester loop globs profiles/rosters/, so staged files are NOT picked
up until a later round moves them in, e.g. after the gate mass run lands).
Never touches backfill_roster_00*.csv.

Dedupe: all existing roster rows (every CSV under profiles/rosters/) +
characters.canonical_name from Postgres (asyncpg via battlebot.common.db).
Prints a JSON summary per franchise: fetched / filtered / net-new / path.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.common.db import connect_database
from battlebot.harvest.category_enumerate import (
    VERSE_CATEGORIES,
    dedupe_rows,
    fetch_category_members,
    filter_members,
    roster_rows,
)
from battlebot.rosters.expand import ROSTER_HEADER, read_roster_rows

STAGING_DIR = Path("profiles/rosters-staging")
ROSTER_DIR = Path("profiles/rosters")


def slugify(franchise: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", franchise.lower()).strip("_")


async def load_db_names() -> set[str]:
    async with connect_database() as connection:
        rows = await connection.fetch("SELECT canonical_name FROM characters")
    return {str(row["canonical_name"]).casefold() for row in rows if row["canonical_name"]}


def load_existing_keys(roster_dir: Path) -> set[tuple[str, str, str]]:
    rows = read_roster_rows(roster_dir, include_generated_outputs=True)
    return {(row.category.casefold(), row.franchise.casefold(), row.name.casefold()) for row in rows}


def run_franchise(
    category: str,
    franchise: str,
    wiki_category: str,
    existing_keys: set[tuple[str, str, str]],
    db_names: set[str],
    staging_dir: Path,
    dry_run: bool,
) -> dict:
    raw = fetch_category_members(wiki_category)
    display = wiki_category.replace("_", " ")
    filtered = filter_members(raw, exclude=(display, franchise))
    rows = dedupe_rows(roster_rows(category, franchise, filtered), existing_keys, db_names)
    path = staging_dir / f"franchise_20261025_{slugify(franchise)}.csv"
    if rows and not dry_run:
        staging_dir.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=ROSTER_HEADER)
            writer.writeheader()
            writer.writerows(rows)
    return {
        "category": category,
        "franchise": franchise,
        "wiki_category": wiki_category,
        "fetched": len(raw),
        "filtered": len(filtered),
        "net_new": len(rows),
        "path": str(path) if rows else "",
        "written": bool(rows and not dry_run),
    }


def select_franchises(names: list[str] | None) -> list[tuple[str, str, str]]:
    selected = []
    for (category, franchise), wiki_category in VERSE_CATEGORIES.items():
        if names and franchise not in names:
            continue
        selected.append((category, franchise, wiki_category))
    if names:
        missing = set(names) - {franchise for _, franchise, _ in selected}
        if missing:
            raise SystemExit(f"unknown franchise(s) (not in VERSE_CATEGORIES): {sorted(missing)}")
    return selected


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--franchise", action="append", default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.all and not args.franchise:
        raise SystemExit("pass --all or --franchise <name> (repeatable)")
    selected = select_franchises(args.franchise)
    existing_keys = load_existing_keys(ROSTER_DIR)
    db_names = await load_db_names()
    summary = {}
    for category, franchise, wiki_category in selected:
        summary[franchise] = run_franchise(
            category, franchise, wiki_category, existing_keys, db_names, STAGING_DIR, args.dry_run
        )
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
