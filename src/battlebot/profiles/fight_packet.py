"""Build compact non-LLM fight packets from resolved profiles."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import re

from battlebot.profiles.locate import locate_character
from battlebot.profiles.quality import profile_warning_flags
from battlebot.profiles.store import resolve_character


CORE_POWER_AXES = (
    "tier",
    "attack_potency",
    "speed",
    "durability",
    "range",
    "stamina",
    "intelligence",
)
OPTIONAL_TACTICAL_FIELDS = (
    "combat_style",
    "win_conditions",
    "losing_conditions",
    "loss_conditions",
    "counters",
    "resistances",
    "battlefield_control",
    "tactical_intelligence",
    "forms",
    "equipment_loadout",
    "matchup_notes",
)


def compact_power_entry(entry: Any) -> str | None:
    if isinstance(entry, dict):
        text = entry.get("text")
        return str(text) if text and "|" not in str(text) else None
    if entry:
        return str(entry) if "|" not in str(entry) else None
    return None


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "tags": item.get("tags") or [],
        "confidence": item.get("confidence"),
        "source_ids": item.get("source_ids") or [],
        **{key: item.get(key) for key in ("activation_requirements", "counters", "resource_dependencies", "scope_limitations") if item.get(key)},
    }


def compact_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": source.get("id"),
        "title": source.get("title"),
        "url": source.get("url"),
        "source_type": source.get("source_type"),
        "revision_id": source.get("revision_id"),
    }


def compact_profile(
    profile: dict[str, Any],
    *,
    ability_limit: int = 12,
    equipment_limit: int = 8,
    weakness_limit: int = 8,
    source_limit: int = 5,
) -> dict[str, Any]:
    profile_json = profile["profile_json"]
    from battlebot.profiles.readiness import assess_readiness
    readiness = assess_readiness(profile_json)
    power_scale = profile_json.get("power_scale") or {}
    from battlebot.profiles.evidence_quality import usable_item
    abilities = [x for x in profile_json.get("abilities") or [] if usable_item(x)]
    resistances = [x for x in profile_json.get("resistances") or [] if usable_item(x)]
    equipment = profile_json.get("equipment") or []
    weaknesses = profile_json.get("weaknesses") or []
    sources = profile_json.get("sources") or []
    used_sources = set()
    for item in [*abilities[:ability_limit], *resistances[:ability_limit], *equipment[:equipment_limit], *weaknesses[:weakness_limit], *power_scale.values()]:
        if isinstance(item, dict):
            used_sources.update(item.get("source_ids") or [])
    # Preserve every source cited by the selected evidence; cap only uncited extras.
    sources = [x for x in sources if x.get("id") in used_sources] if used_sources else sources[:source_limit]
    return {
        "character_id": profile["character_id"],
        "canonical_name": profile["canonical_name"],
        "franchise": profile["franchise"],
        "category": profile["category"],
        "profile_id": profile["profile_id"],
        "profile_hash": profile["profile_hash"],
        "profile_type": profile["profile_type"],
        "variant": profile_json.get("variant") or {},
        "readiness": readiness,
        "interaction_tags": profile_json.get("interaction_tags") or [],
        "resource_dependencies": profile_json.get("resource_dependencies") or [],
        "power_source": profile_json.get("power_source"),
        "power_scale": {
            axis: compact_power_entry(power_scale.get(axis)) for axis in CORE_POWER_AXES
        },
        "power_scale_source_ids": {axis: (power_scale.get(axis) or {}).get("source_ids", []) if isinstance(power_scale.get(axis), dict) else [] for axis in CORE_POWER_AXES},
        "abilities": [
            compact_item(item)
            for item in abilities
            if not re.search(r"(?i)border|scroll\s*=|visible\s*=|padding\s*=|content\s*=|\{\{|tabber", str(item.get("name") or ""))
        ][:ability_limit],
        "ability_count": len(abilities),
        "resistances": [compact_item(item) for item in resistances[:ability_limit]],
        "resistance_count": len(resistances),
        "equipment": [compact_item(item) for item in equipment[:equipment_limit]],
        "equipment_count": len(equipment),
        "weaknesses": [compact_item(item) for item in weaknesses[:weakness_limit]],
        "weakness_count": len(weaknesses),
        "sources": [compact_source(source) for source in sources],
        "source_count": len(sources),
        "claims": [{key: claim.get(key) for key in ("text", "claim_text", "axis", "source_ids")} for claim in (profile_json.get("claims") or [])[:6]],
        "warnings": profile_warning_flags(profile),
        "tactical_profile": {
            key: profile_json.get(key)
            for key in OPTIONAL_TACTICAL_FIELDS
            if profile_json.get(key) not in (None, "", [], {})
        },
    }


def ordered_pair_key(character_a_id: str, character_b_id: str) -> str:
    return "::".join(sorted([character_a_id, character_b_id]))


async def resolution_error(
    connection: Any,
    label: str,
    resolution: dict[str, Any],
) -> dict[str, Any]:
    error = {
        "contender": label,
        "status": resolution["status"],
        "query": resolution["query"],
    }
    if resolution["status"] == "ambiguous":
        error["candidates"] = resolution.get("candidates", [])
        error["disambiguation_options"] = resolution.get("disambiguation_options", [])
    if resolution["status"] == "not_found":
        error["diagnostics"] = await locate_character(resolution["query"], connection=connection)
    if resolution.get("reason"):
        error["reason"] = resolution["reason"]
        error["message"] = resolution.get("message")
    if resolution.get("alias_match"):
        error["alias_match"] = resolution["alias_match"]
    if resolution.get("canonical_not_battle_ready"):
        error["canonical_not_battle_ready"] = True
    return error


async def build_fight_packet(
    connection: Any,
    contender_a: str,
    contender_b: str,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolution_a = await resolve_character(connection, contender_a)
    resolution_b = await resolve_character(connection, contender_b)
    errors = []
    if resolution_a["status"] != "resolved":
        errors.append(await resolution_error(connection, "contender_a", resolution_a))
    if resolution_b["status"] != "resolved":
        errors.append(await resolution_error(connection, "contender_b", resolution_b))

    packet: dict[str, Any] = {
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "rules": {"default_form": "canonical_base", "energy_equalization": False, "conditional_assessment": True,
                  "genjutsu_requires_chakra": True, "stand_perception_requires_stand": True,
                  **(rules or {})},
        "errors": errors,
    }
    if errors:
        packet["contender_a"] = resolution_a
        packet["contender_b"] = resolution_b
        packet["profile_hashes"] = []
        packet["ordered_pair_key"] = None
        return packet

    compact_a = compact_profile(resolution_a["profile"])
    compact_b = compact_profile(resolution_b["profile"])
    from battlebot.fight.literal_rules import apply_literal_rules
    compact_a, compact_b = apply_literal_rules(compact_a, compact_b, packet["rules"])
    packet["contender_a"] = compact_a
    packet["contender_b"] = compact_b
    packet["profile_hashes"] = [compact_a["profile_hash"], compact_b["profile_hash"]]
    packet["ordered_pair_key"] = ordered_pair_key(
        compact_a["character_id"],
        compact_b["character_id"],
    )
    packet["warnings"] = [
        {"contender": "contender_a", **warning}
        for warning in compact_a.get("warnings", [])
    ] + [
        {"contender": "contender_b", **warning}
        for warning in compact_b.get("warnings", [])
    ]
    return packet
