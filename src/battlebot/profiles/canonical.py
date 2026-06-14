"""Canonical display-name helpers for search and duplicate audits."""

from __future__ import annotations

import re
from typing import Any


TRUE_VARIANT_MARKERS = {
    "base",
    "super saiyan",
    "super saiyan blue",
    "ultra instinct",
    "hellbat armor",
    "bleeding edge",
    "hulkbuster",
    "kingdom hearts",
}

DUPLICATE_SUFFIX_MARKERS = {
    "crossover icons",
    "final fantasy",
    "final fantasy vii",
    "dragon ball",
    "marvel",
    "dc",
}


def normalize_text(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", value.casefold())
    return re.sub(r"\s+", " ", text).strip()


def row_display_name(row: dict[str, Any]) -> str:
    profile_json = row.get("profile_json") if isinstance(row.get("profile_json"), dict) else {}
    return str(profile_json.get("name") or row.get("canonical_name") or row.get("name") or "").strip()


def parenthetical_parts(name: str) -> tuple[str, str | None]:
    match = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", name.strip())
    if not match:
        return name.strip(), None
    return match.group(1).strip(), match.group(2).strip()


def canonical_character_key(name: str) -> str:
    base, parenthetical = parenthetical_parts(name)
    if parenthetical:
        marker = normalize_text(parenthetical)
        if marker in TRUE_VARIANT_MARKERS:
            return normalize_text(f"{base} ({parenthetical})")
        return normalize_text(base)
    for separator in (" - ", " – ", " — "):
        if separator in name:
            candidate, suffix = name.split(separator, 1)
            if normalize_text(suffix) in DUPLICATE_SUFFIX_MARKERS:
                return normalize_text(candidate)
    return normalize_text(name)


def row_canonical_group_key(row: dict[str, Any]) -> str:
    return canonical_character_key(row_display_name(row) or str(row.get("canonical_name") or ""))


def is_likely_variant_name(name: str) -> bool:
    _, parenthetical = parenthetical_parts(name)
    return bool(parenthetical and normalize_text(parenthetical) in TRUE_VARIANT_MARKERS)
