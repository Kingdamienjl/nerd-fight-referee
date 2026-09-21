"""Human-readable character profile sheets."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import yaml

from battlebot.common.db import connect_database
from battlebot.profiles.power_display import clean_public_text, public_power_scale
from battlebot.profiles.search import search_characters
from battlebot.profiles.store import resolve_character
from battlebot.review import service


def text_power(profile: dict[str, Any], field: str) -> str:
    return service.power_text(profile, field) or "n/a"


def item_line(item: dict[str, Any]) -> str:
    name = clean_public_text(item.get("name") or item.get("id") or "item")
    description = clean_public_text(item.get("description") or "")
    return f"- {name}: {description[:160]}"


def summary_text(profile: dict[str, Any], field: str) -> str:
    return clean_public_text(text_power(profile, field))


def abilities_summary(abilities: list[dict[str, Any]]) -> str:
    if not abilities:
        return "none listed"
    names = [clean_public_text(item.get("name") or item.get("id") or "ability") for item in abilities[:5]]
    suffix = f" (+{len(abilities) - 5} more)" if len(abilities) > 5 else ""
    return ", ".join(names) + suffix


def public_profile_status(profile: dict[str, Any], warnings: list[str], source_backed: bool) -> str:
    status = str(profile.get("status") or "").casefold()
    if status in {"verified", "approved"}:
        return "Verified"
    return "Verified" if source_backed and not warnings else "Provisional"


def yaml_profile_sheet(path: Path) -> str:
    profile = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return format_profile_data(profile, status=path.parts[path.parts.index("profiles") + 1] if "profiles" in path.parts else "yaml", profile_path=str(path))


def imported_profile_to_data(profile: dict[str, Any]) -> dict[str, Any]:
    data = dict(profile["profile_json"])
    data.setdefault("name", profile["canonical_name"])
    data.setdefault("franchise", profile["franchise"])
    data.setdefault("category", profile["category"])
    data["profile_hash"] = profile.get("profile_hash")
    data["status"] = profile.get("status")
    data["battle_eligible"] = profile.get("battle_eligible")
    return data


def format_profile_data(profile: dict[str, Any], *, status: str, profile_path: str = "") -> str:
    sources = profile.get("sources") or []
    abilities = profile.get("abilities") or []
    warnings = [warning["flag"] for warning in service.profile_warning_flags(profile)] if hasattr(service, "profile_warning_flags") else []
    source_backed = any(source.get("url") or source.get("revision_id") for source in sources)
    power_scale = public_power_scale(text_power(profile, "tier"))
    profile_status = public_profile_status(profile, warnings, source_backed)
    lines = [
        f"Name: {clean_public_text(profile.get('name'))}",
        f"Franchise: {clean_public_text(profile.get('franchise'))}",
        f"Category: {clean_public_text(profile.get('category'))}",
        f"Battle Ready: {bool(profile.get('battle_eligible'))}",
        f"Source-backed: {'yes' if source_backed else 'no'}",
        f"Source count: {len(sources)}",
        f"Profile Status: {profile_status}",
        f"Threat Rating: {power_scale.damage_class}",
        f"Destruction Scale: {power_scale.footprint}",
        f"Attack summary: {summary_text(profile, 'attack_potency')}",
        f"Speed summary: {summary_text(profile, 'speed')}",
        f"Durability summary: {summary_text(profile, 'durability')}",
        f"Abilities summary: {abilities_summary(abilities)}",
    ]
    return "\n".join(lines)


async def profile_sheet(
    character_query: str,
    database_url: str | None = None,
    *,
    connection: Any | None = None,
) -> str:
    if connection is not None:
        resolution = await resolve_character(connection, character_query, battle_eligible_only=False)
    elif database_url:
        async with connect_database(database_url) as db:
            resolution = await resolve_character(db, character_query, battle_eligible_only=False)
    else:
        resolution = {"status": "not_found"}
    if resolution.get("status") == "resolved":
        profile = resolution["profile"]
        return format_profile_data(imported_profile_to_data(profile), status="imported")
    rows = await search_characters(character_query, connection=connection, database_url=database_url, limit=5)
    for row in rows:
        path = row.get("profile_path")
        if path and Path(path).suffix == ".yaml" and Path(path).exists():
            return yaml_profile_sheet(Path(path))
    return "Profile not found."


async def async_main(args: argparse.Namespace) -> int:
    print(await profile_sheet(args.character, args.database_url))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a battle profile sheet")
    parser.add_argument("character")
    parser.add_argument("--database-url")
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
