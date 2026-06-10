"""Character search across DB, generated YAML, needs_review YAML, aliases, and rosters."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path
from typing import Any

import yaml

from battlebot.common.db import connect_database
from battlebot.profiles.aliases import resolve_alias
from battlebot.profiles.locate import find_db_name_matches
from battlebot.profiles.quality import profile_key
from battlebot.review import service


def profile_matches(path: Path, query: str) -> bool:
    key = profile_key(query)
    if not key:
        return True
    haystack = profile_key(" ".join(path.with_suffix("").parts))
    if key in haystack:
        return True
    parts = [part for part in key.split("-") if len(part) > 2]
    return bool(parts) and all(part in haystack for part in parts)


def reason_not_ready(profile: dict[str, Any]) -> str:
    blockers = service.approval_blockers(profile)
    if blockers:
        return ", ".join(blockers[:4])
    generation = profile.get("generation") or {}
    reasons = generation.get("ineligible_reasons") or []
    return ", ".join(str(reason) for reason in reasons[:4]) or "not imported"


def yaml_search_rows(query: str, root: Path, status: str, *, limit: int) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.rglob("*.yaml")):
        if not profile_matches(path.relative_to(root), query):
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows.append(
            {
                "canonical_name": data.get("name") or path.stem,
                "franchise": data.get("franchise"),
                "category": data.get("category"),
                "status": status,
                "battle_ready": bool(data.get("battle_eligible")) and status == "generated",
                "profile_path": str(path),
                "reason": "" if data.get("battle_eligible") else reason_not_ready(data),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def roster_search_rows(query: str, rosters_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    if not rosters_dir.exists():
        return []
    needle = query.casefold()
    rows = []
    for csv_path in sorted(rosters_dir.rglob("*.csv")):
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                haystack = " ".join(str(value or "") for value in row.values()).casefold()
                if needle not in haystack:
                    continue
                rows.append(
                    {
                        "canonical_name": row.get("name"),
                        "franchise": row.get("franchise"),
                        "category": row.get("category"),
                        "status": "roster_stub",
                        "battle_ready": False,
                        "profile_path": str(csv_path),
                        "reason": "roster only",
                    }
                )
                if len(rows) >= limit:
                    return rows
    return rows


async def db_search_rows(connection: Any, query: str, *, limit: int) -> list[dict[str, Any]]:
    matches = await find_db_name_matches(connection, query, limit=limit)
    return [
        {
            "canonical_name": match["canonical_name"],
            "franchise": match["franchise"],
            "category": match["category"],
            "status": "imported",
            "battle_ready": True,
            "character_id": match["character_id"],
            "profile_path": "",
            "reason": "",
        }
        for match in matches
    ]


def dedupe_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for row in rows:
        key = (str(row.get("canonical_name") or "").casefold(), row.get("franchise"), row.get("status"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
        if len(unique) >= limit:
            break
    return unique


async def search_characters(
    query: str,
    database_url: str | None = None,
    *,
    connection: Any | None = None,
    status_filter: str | None = None,
    category: str | None = None,
    franchise: str | None = None,
    limit: int = 10,
    generated_dir: Path | str = "profiles/generated",
    needs_review_dir: Path | str = "profiles/needs_review",
    rosters_dir: Path | str = "profiles/rosters",
) -> list[dict[str, Any]]:
    alias_match = resolve_alias(query)
    search_query = alias_match.canonical if alias_match else query
    rows: list[dict[str, Any]] = []
    if connection is not None:
        rows.extend(await db_search_rows(connection, search_query, limit=limit))
    elif database_url:
        async with connect_database(database_url) as db:
            rows.extend(await db_search_rows(db, search_query, limit=limit))
    rows.extend(yaml_search_rows(search_query, Path(generated_dir), "generated", limit=limit))
    rows.extend(yaml_search_rows(search_query, Path(needs_review_dir), "needs_review", limit=limit))
    rows.extend(roster_search_rows(search_query, Path(rosters_dir), limit=limit))
    if alias_match:
        for row in rows:
            row["alias_used"] = query
            row["alias_canonical"] = alias_match.canonical
    if status_filter and status_filter != "all":
        rows = [row for row in rows if row.get("status") == status_filter]
    if category:
        rows = [row for row in rows if str(row.get("category") or "").casefold() == category.casefold()]
    if franchise:
        rows = [row for row in rows if str(row.get("franchise") or "").casefold() == franchise.casefold()]
    return dedupe_rows(rows, limit)


def format_search_results(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No characters found."
    lines = []
    for index, row in enumerate(rows, start=1):
        ready = "battle ready" if row.get("battle_ready") else row.get("reason") or "not battle ready"
        alias = f" alias:{row['alias_used']}->{row['alias_canonical']}" if row.get("alias_used") else ""
        lines.append(
            f"{index}. {row.get('canonical_name')} - {row.get('franchise')}/{row.get('category')} - "
            f"{row.get('status')} - {ready}{alias}"
        )
    return "\n".join(lines)


async def async_main(args: argparse.Namespace) -> int:
    rows = await search_characters(
        args.query,
        args.database_url,
        status_filter=args.status,
        category=args.category,
        franchise=args.franchise,
        limit=args.limit,
    )
    print(json.dumps(rows, indent=2) if args.json else format_search_results(rows))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search battlebot characters")
    parser.add_argument("query")
    parser.add_argument("--database-url")
    parser.add_argument("--status")
    parser.add_argument("--category")
    parser.add_argument("--franchise")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
