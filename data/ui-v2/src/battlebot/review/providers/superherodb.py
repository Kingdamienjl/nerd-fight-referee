"""SuperHeroDB HTML adapter for cross-check metadata."""

from __future__ import annotations

import re
from html import unescape


def clean_html_text(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()


def parse_superherodb_html(content: str) -> dict[str, str]:
    text = clean_html_text(content)
    fields: dict[str, str] = {}
    alias_match = re.search(r"Aliases?\s*[:\-]\s*([^|]+?)(?:Place of Birth|First Appearance|Publisher|$)", text, re.I)
    if alias_match:
        fields["aliases"] = alias_match.group(1).strip()
    powers_match = re.search(r"(?:Powers?|Abilities)\s*[:\-]\s*(.+?)(?:Power Grid|Stats|$)", text, re.I)
    if powers_match:
        fields["powers_and_abilities"] = powers_match.group(1).strip()
    stat_parts = []
    for label in ("Intelligence", "Strength", "Speed", "Durability", "Power", "Combat"):
        match = re.search(rf"{label}\s*[:\-]?\s*(\d{{1,3}})", text, re.I)
        if match:
            stat_parts.append(f"{label}: {match.group(1)}")
    if stat_parts:
        fields["stat_notes"] = "; ".join(stat_parts)
    return fields
