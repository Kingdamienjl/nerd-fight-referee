"""Database-backed character profile lookup."""

from __future__ import annotations

import json
import re
from typing import Any


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
        "imported_at": data.get("imported_at"),
        "updated_at": data.get("updated_at"),
    }


def candidate_summary(profile: dict[str, Any]) -> dict[str, str]:
    return {
        "character_id": profile["character_id"],
        "canonical_name": profile["canonical_name"],
        "franchise": profile["franchise"],
        "category": profile["category"],
        "profile_id": profile["profile_id"],
    }


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
        return {
            "status": "ambiguous",
            "query": query,
            "matched_by": matched_by,
            "candidates": [candidate_summary(candidate) for candidate in candidates[:8]],
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
        return resolution_from_candidates(
            name,
            case_insensitive,
            matched_by="canonical_case_insensitive",
        )

    alias = await fetch_alias(connection, name, battle_eligible_only=battle_eligible_only)
    if alias:
        return resolution_from_candidates(name, alias, matched_by="alias")

    return {"status": "not_found", "query": name, "candidates": []}
