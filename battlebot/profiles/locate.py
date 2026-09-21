"""Locate a character across imported DB rows and local profile files."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path
from typing import Any

from battlebot.common.db import connect_database
from battlebot.profiles.aliases import resolve_alias
from battlebot.profiles.quality import profile_key


def path_matches_term(path: Path, term: str) -> bool:
    needle = profile_key(term)
    haystack = profile_key(" ".join(path.with_suffix("").parts))
    if needle in haystack:
        return True
    parts = [part for part in needle.split("-") if len(part) > 2]
    return bool(parts) and all(part in haystack for part in parts)


def find_yaml_matches(term: str, base_dir: Path | str, *, limit: int = 12) -> list[str]:
    root = Path(base_dir)
    if not root.exists():
        return []
    matches = [
        str(path)
        for path in sorted(root.rglob("*.yaml"))
        if path_matches_term(path.relative_to(root), term)
    ]
    return matches[:limit]


def find_roster_matches(term: str, rosters_dir: Path | str, *, limit: int = 12) -> list[dict[str, str]]:
    root = Path(rosters_dir)
    if not root.exists():
        return []
    needle = term.casefold()
    matches: list[dict[str, str]] = []
    for csv_path in sorted(root.rglob("*.csv")):
        try:
            with csv_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    haystack = " ".join(str(value or "") for value in row.values()).casefold()
                    if needle in haystack:
                        matches.append({"path": str(csv_path), **{k: str(v or "") for k, v in row.items()}})
                    if len(matches) >= limit:
                        return matches
        except OSError:
            continue
    return matches


async def find_db_name_matches(connection: Any, term: str, *, limit: int = 8) -> list[dict[str, str]]:
    fragments = [part for part in profile_key(term).split("-") if len(part) > 2]
    if not fragments:
        fragments = [term]
    pattern = f"%{fragments[0]}%"
    rows = await connection.fetch(
        """
SELECT id AS character_id, canonical_name, franchise, category
FROM characters
WHERE canonical_name ILIKE $1
ORDER BY canonical_name
LIMIT $2
""",
        pattern,
        limit,
    )
    return [
        {
            "character_id": str(row["character_id"]),
            "canonical_name": str(row["canonical_name"]),
            "franchise": str(row["franchise"]),
            "category": str(row["category"]),
        }
        for row in rows
    ]


async def locate_character(
    term: str,
    *,
    connection: Any | None = None,
    generated_dir: Path | str = "profiles/generated",
    needs_review_dir: Path | str = "profiles/needs_review",
    rosters_dir: Path | str = "profiles/rosters",
) -> dict[str, Any]:
    alias_match = resolve_alias(term)
    canonical_term = alias_match.canonical if alias_match else term
    result: dict[str, Any] = {
        "query": term,
        "alias_match": {
            "canonical": alias_match.canonical,
            "matched_key": alias_match.matched_key,
            "notes": alias_match.notes,
        }
        if alias_match
        else None,
        "db_matches": [],
        "generated_paths": find_yaml_matches(canonical_term, generated_dir),
        "needs_review_paths": find_yaml_matches(canonical_term, needs_review_dir),
        "roster_rows": find_roster_matches(canonical_term, rosters_dir),
    }
    if connection is not None:
        result["db_matches"] = await find_db_name_matches(connection, canonical_term)
    return result


def format_locate_result(result: dict[str, Any]) -> str:
    lines = [f"Locate: {result['query']}"]
    if result.get("alias_match"):
        lines.append(f"Alias: {result['query']} -> {result['alias_match']['canonical']}")
    db_matches = result.get("db_matches") or []
    lines.append(f"DB matches: {len(db_matches)}")
    for match in db_matches[:8]:
        lines.append(
            f"- {match['canonical_name']} ({match['franchise']}, {match['category']})"
        )

    for label, key in (
        ("generated YAML paths", "generated_paths"),
        ("needs_review YAML paths", "needs_review_paths"),
    ):
        values = result.get(key) or []
        lines.append(f"{label}: {len(values)}")
        for value in values[:8]:
            lines.append(f"- {value}")

    roster_rows = result.get("roster_rows") or []
    lines.append(f"roster CSV rows: {len(roster_rows)}")
    for row in roster_rows[:5]:
        lines.append(
            f"- {row.get('path')}: {row.get('category')}, "
            f"{row.get('franchise')}, {row.get('name')}"
        )
    return "\n".join(lines)


async def async_main(args: argparse.Namespace) -> int:
    if args.database_url:
        async with connect_database(args.database_url) as connection:
            result = await locate_character(
                args.term,
                connection=connection,
                generated_dir=args.generated_dir,
                needs_review_dir=args.needs_review_dir,
                rosters_dir=args.rosters_dir,
            )
    else:
        result = await locate_character(
            args.term,
            generated_dir=args.generated_dir,
            needs_review_dir=args.needs_review_dir,
            rosters_dir=args.rosters_dir,
        )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_locate_result(result))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Locate a character across DB and profile files")
    parser.add_argument("term")
    parser.add_argument("--database-url")
    parser.add_argument("--generated-dir", default="profiles/generated")
    parser.add_argument("--needs-review-dir", default="profiles/needs_review")
    parser.add_argument("--rosters-dir", default="profiles/rosters")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
