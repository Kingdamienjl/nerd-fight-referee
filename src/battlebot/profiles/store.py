"""Database-backed character profile lookup."""

from __future__ import annotations

import json
import re
from typing import Any

from battlebot.profiles.aliases import resolve_alias
from battlebot.profiles.canonical import row_display_name


CORE_PROFILE_SELECT = """
SELECT DISTINCT ON (c.id)
    c.id AS character_id,
    c.canonical_name,
    c.franchise,
    c.category,
    cp.profile_id,
    cp.profile_type,
    cp.status,
    cp.battle_eligible,
    cp.profile_hash,
    cp.profile_json,
    cp.imported_at,
    cp.updated_at
FROM characters c
JOIN character_profiles cp ON cp.character_id = c.id
"""


def normalize_lookup(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def decode_profile_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    return {}


def row_to_profile(row: Any) -> dict[str, Any]:
    data = dict(row)
    profile_json = decode_profile_json(data.get("profile_json"))
    return {
        "character_id": data["character_id"],
        "canonical_name": data["canonical_name"],
        "franchise": data["franchise"],
        "category": data["category"],
        "profile_id": data["profile_id"],
        "profile_type": data["profile_type"],
        "status": data["status"],
        "battle_eligible": data["battle_eligible"],
        "profile_hash": data["profile_hash"],
        "profile_json": profile_json,
        "aliases": data.get("aliases") or [],
        "imported_at": data.get("imported_at"),
        "updated_at": data.get("updated_at"),
    }


def candidate_summary(profile: dict[str, Any]) -> dict[str, str]:
    summary = {}
    for key in ("character_id", "canonical_name", "franchise", "category", "profile_id"):
        value = str(profile.get(key) or "").strip()
        if value:
            summary[key] = value
    display_name = row_display_name(profile)
    if display_name and display_name != profile.get("canonical_name"):
        summary["display_name"] = display_name
    return summary


def disambiguation_options(candidates: list[dict[str, Any]]) -> list[str]:
    options = []
    for index, candidate in enumerate(candidates, start=1):
        summary = candidate_summary(candidate)
        parts = [
            summary.get("display_name") or summary.get("canonical_name"),
            summary.get("franchise"),
            summary.get("category"),
        ]
        label = " - ".join(part for part in parts if part)
        if label:
            options.append(f"{index}. {label}")
    return options


def profile_source_count(profile: dict[str, Any]) -> int:
    profile_json = profile.get("profile_json") if isinstance(profile.get("profile_json"), dict) else {}
    sources = profile_json.get("sources") or []
    return len(sources) if isinstance(sources, list) else 0


def profile_quality_rank(profile: dict[str, Any]) -> int:
    status = str(profile.get("status") or "").casefold()
    profile_type = str(profile.get("profile_type") or "").casefold()
    if status in {"verified", "approved"}:
        return 3
    if status == "provisional":
        return 2
    if status in {"imported", "auto_generated", "generated"} or "generated" in profile_type:
        return 1
    if status == "roster_stub":
        return 0
    return 1


def is_default_variant(profile: dict[str, Any]) -> bool:
    profile_json = profile.get("profile_json") if isinstance(profile.get("profile_json"), dict) else {}
    variant = profile_json.get("variant") if isinstance(profile_json.get("variant"), dict) else {}
    return bool(variant.get("default_variant"))


def canonical_franchise_rank(profile: dict[str, Any]) -> int:
    franchise = normalize_lookup(str(profile.get("franchise") or ""))
    text = " ".join(
        [
            str(profile.get("canonical_name") or ""),
            franchise,
            row_display_name(profile),
        ]
    ).casefold()
    if "crossover icons" in text or str(profile.get("status") or "").casefold() == "roster_stub":
        return -10
    return len(franchise.split())


def non_stub_rank(profile: dict[str, Any]) -> int:
    status = str(profile.get("status") or "").casefold()
    profile_type = str(profile.get("profile_type") or "").casefold()
    return 0 if status == "roster_stub" or "stub" in profile_type else 1


def display_tiebreaker(profile: dict[str, Any]) -> str:
    text = " ".join(
        [
            str(profile.get("canonical_name") or ""),
            str(profile.get("franchise") or ""),
            row_display_name(profile),
        ]
    ).casefold()
    return text


def default_profile_score(profile: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
    return (
        1 if is_default_variant(profile) else 0,
        profile_quality_rank(profile),
        profile_source_count(profile),
        canonical_franchise_rank(profile),
        non_stub_rank(profile),
        display_tiebreaker(profile),
    )


def choose_default_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    ranked = sorted(candidates, key=default_profile_score, reverse=True)
    if len(ranked) == 1:
        return ranked[0]
    return ranked[0] if default_profile_score(ranked[0]) > default_profile_score(ranked[1]) else None


def row_has_alias(profile: dict[str, Any], query: str) -> bool:
    aliases = profile.get("aliases") or []
    query_key = normalize_lookup(query)
    return query_key in {normalize_lookup(str(alias)) for alias in aliases}


async def fetch_exact_canonical(
    connection: Any,
    name: str,
    *,
    battle_eligible_only: bool = True,
) -> list[dict[str, Any]]:
    rows = await connection.fetch(
        CORE_PROFILE_SELECT
        + """
WHERE c.canonical_name = $1
  AND ($2::boolean = false OR cp.battle_eligible = true)
ORDER BY c.id, cp.imported_at DESC, cp.updated_at DESC
""",
        name,
        battle_eligible_only,
    )
    return [row_to_profile(row) for row in rows]


async def fetch_case_insensitive_canonical(
    connection: Any,
    name: str,
    *,
    battle_eligible_only: bool = True,
) -> list[dict[str, Any]]:
    rows = await connection.fetch(
        CORE_PROFILE_SELECT
        + """
WHERE lower(c.canonical_name) = lower($1)
  AND ($2::boolean = false OR cp.battle_eligible = true)
ORDER BY c.id, cp.imported_at DESC, cp.updated_at DESC
""",
        name,
        battle_eligible_only,
    )
    return [row_to_profile(row) for row in rows]


async def fetch_alias(
    connection: Any,
    name: str,
    *,
    battle_eligible_only: bool = True,
) -> list[dict[str, Any]]:
    rows = await connection.fetch(
        CORE_PROFILE_SELECT
        + """
JOIN character_aliases ca ON ca.character_id = c.id
WHERE ca.normalized_alias = $1
  AND ($2::boolean = false OR cp.battle_eligible = true)
ORDER BY c.id, cp.imported_at DESC, cp.updated_at DESC
""",
        normalize_lookup(name),
        battle_eligible_only,
    )
    return [row_to_profile(row) for row in rows]


def resolution_from_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    matched_by: str,
) -> dict[str, Any]:
    if not candidates:
        return {"status": "not_found", "query": query, "candidates": []}
    if len(candidates) > 1:
        default = choose_default_candidate(candidates)
        if default:
            return {
                "status": "resolved",
                "query": query,
                "matched_by": f"{matched_by}_default",
                "profile": default,
            }
        return {
            "status": "ambiguous",
            "query": query,
            "matched_by": matched_by,
            "candidates": [candidate_summary(candidate) for candidate in candidates[:8]],
            "disambiguation_options": disambiguation_options(candidates[:8]),
        }
    return {
        "status": "resolved",
        "query": query,
        "matched_by": matched_by,
        "profile": candidates[0],
    }


async def resolve_character(
    connection: Any,
    name: str,
    *,
    battle_eligible_only: bool = True,
) -> dict[str, Any]:
    exact = await fetch_exact_canonical(
        connection,
        name,
        battle_eligible_only=battle_eligible_only,
    )
    if exact:
        return resolution_from_candidates(name, exact, matched_by="canonical_exact")

    case_insensitive = await fetch_case_insensitive_canonical(
        connection,
        name,
        battle_eligible_only=battle_eligible_only,
    )
    if case_insensitive:
        return resolution_from_candidates(name, case_insensitive, matched_by="canonical_case_insensitive")

    alias_override = resolve_alias(name)
    if alias_override:
        override_exact = await fetch_exact_canonical(
            connection,
            alias_override.canonical,
            battle_eligible_only=battle_eligible_only,
        )
        if override_exact:
            matched_by = "alias" if any(row_has_alias(profile, name) for profile in override_exact) else "alias_override"
            result = resolution_from_candidates(name, override_exact, matched_by=matched_by)
            result["alias_match"] = {
                "canonical": alias_override.canonical,
                "matched_key": alias_override.matched_key,
                "notes": alias_override.notes,
            }
            return result

        override_case = await fetch_case_insensitive_canonical(
            connection,
            alias_override.canonical,
            battle_eligible_only=battle_eligible_only,
        )
        if override_case:
            matched_by = "alias" if any(row_has_alias(profile, name) for profile in override_case) else "alias_override"
            result = resolution_from_candidates(name, override_case, matched_by=matched_by)
            result["alias_match"] = {
                "canonical": alias_override.canonical,
                "matched_key": alias_override.matched_key,
                "notes": alias_override.notes,
            }
            return result

    alias = await fetch_alias(connection, name, battle_eligible_only=battle_eligible_only)
    if alias:
        return resolution_from_candidates(name, alias, matched_by="alias")

    result = {"status": "not_found", "query": name, "candidates": []}
    if alias_override:
        result["alias_match"] = {
            "canonical": alias_override.canonical,
            "matched_key": alias_override.matched_key,
            "notes": alias_override.notes,
        }
        result["canonical_not_battle_ready"] = True
    return result
