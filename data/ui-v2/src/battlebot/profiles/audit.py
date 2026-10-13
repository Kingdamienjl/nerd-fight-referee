"""Audit imported character profiles for obvious quality problems."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from battlebot.common.db import connect_database
from battlebot.profiles.quality import (
    ability_count,
    power_text,
    profile_warning_flags,
    source_rows,
    warning_flags_only,
    weakness_count,
)
from battlebot.profiles.store import CORE_PROFILE_SELECT, resolve_character, row_to_profile


def source_summary(profile: dict[str, Any]) -> list[str]:
    summaries = []
    for source in source_rows(profile)[:5]:
        title = source.get("title") or source.get("id") or "unknown"
        revision = source.get("revision_id") or "n/a"
        summaries.append(f"{title} rev={revision}")
    return summaries


def audit_profile(profile: dict[str, Any]) -> dict[str, Any]:
    warnings = profile_warning_flags(profile)
    return {
        "character_name": profile["canonical_name"],
        "franchise": profile["franchise"],
        "category": profile["category"],
        "profile_id": profile["profile_id"],
        "attack_potency": power_text(profile, "attack_potency"),
        "speed": power_text(profile, "speed"),
        "durability": power_text(profile, "durability"),
        "ability_count": ability_count(profile),
        "weakness_count": weakness_count(profile),
        "sources": source_summary(profile),
        "warnings": warnings,
        "warning_flags": warning_flags_only(warnings),
    }


def format_audit(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No profiles found."
    lines: list[str] = []
    for row in rows:
        lines.extend(
            [
                f"{row['character_name']} ({row['franchise']}, {row['category']})",
                f"  profile: {row['profile_id']}",
                f"  attack: {row['attack_potency'] or 'n/a'}",
                f"  speed: {row['speed'] or 'n/a'}",
                f"  durability: {row['durability'] or 'n/a'}",
                f"  abilities: {row['ability_count']} weaknesses: {row['weakness_count']}",
                f"  sources: {', '.join(row['sources']) if row['sources'] else 'n/a'}",
                f"  warnings: {', '.join(row['warning_flags']) if row['warning_flags'] else 'none'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


async def fetch_all_profiles(connection: Any) -> list[dict[str, Any]]:
    rows = await connection.fetch(
        CORE_PROFILE_SELECT
        + """
ORDER BY c.id, cp.imported_at DESC, cp.updated_at DESC
"""
    )
    return [row_to_profile(row) for row in rows]


async def async_main(args: argparse.Namespace) -> int:
    async with connect_database(args.database_url) as connection:
        if args.character:
            resolution = await resolve_character(
                connection,
                args.character,
                battle_eligible_only=False,
            )
            profiles = [resolution["profile"]] if resolution["status"] == "resolved" else []
        else:
            profiles = await fetch_all_profiles(connection)

    audited = [audit_profile(profile) for profile in profiles]
    if args.weak_threshold:
        audited = [row for row in audited if row["warnings"]]
    print(format_audit(audited))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit imported battle profiles")
    parser.add_argument("--database-url")
    parser.add_argument("--character")
    parser.add_argument(
        "--weak-threshold",
        action="store_true",
        help="Only print profiles with warning flags.",
    )
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
