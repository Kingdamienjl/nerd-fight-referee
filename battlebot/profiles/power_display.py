"""Display-only public damage classifications."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


TIER_PATTERN = re.compile(r"\b(?:(?:Low|High)\s+)?(?:10-[ABC]|9-[ABC]|8-[ABC]|7-[ABC]|6-[ABC]|5-[ABC]|4-[ABC]|3-[ABC]|2-[ABC]|1-[ABC]|0)\b", re.I)

TIER_DAMAGE_CLASS = {
    "10-C": "Human-Level",
    "10-B": "Human-Level",
    "10-A": "Human-Level",
    "9-C": "Street Fighter",
    "9-B": "Wall-Breaker",
    "9-A": "Room-Wrecker",
    "8-C": "Building-Buster",
    "High 8-C": "Skyscraper-Buster",
    "8-B": "Block-Buster",
    "8-A": "Multi-Block Buster",
    "Low 7-C": "Town-Level Threat",
    "7-C": "Town-Level Threat",
    "High 7-C": "Town-Level Threat",
    "Low 7-B": "City-Level Threat",
    "7-B": "City-Level Threat",
    "7-A": "Mountain-Buster",
    "High 7-A": "Mountain-Buster",
    "6-C": "Island-Buster",
    "High 6-C": "Island-Buster",
    "Low 6-B": "Country-Level Threat",
    "6-B": "Country-Level Threat",
    "High 6-B": "Country-Level Threat",
    "6-A": "Continental Threat",
    "High 6-A": "Continental Threat",
    "5-C": "Planetary Threat",
    "Low 5-B": "Planetary Threat",
    "5-B": "Planetary Threat",
    "5-A": "Planetary Threat",
    "Low 4-C": "Stellar Threat",
    "4-C": "Stellar Threat",
    "High 4-C": "Stellar Threat",
    "4-B": "Stellar Threat",
    "4-A": "Stellar Threat",
    "3-C": "Cosmic Threat",
    "3-B": "Cosmic Threat",
    "3-A": "Cosmic Threat",
    "High 3-A": "Cosmic Threat",
    "Low 2-C": "Multiversal Threat",
    "2-C": "Multiversal Threat",
    "2-B": "Multiversal Threat",
    "2-A": "Multiversal Threat",
    "1-C": "Reality-Breaker",
    "1-B": "Reality-Breaker",
    "1-A": "Reality-Breaker",
    "0": "Reality-Breaker",
}

TIER_FOOTPRINT = {
    "10-C": "normal human → athlete",
    "10-B": "normal human → athlete",
    "10-A": "normal human → athlete",
    "9-C": "person-to-person combat threat",
    "9-B": "stone, steel, walls, heavy barriers",
    "9-A": "room → small structure",
    "8-C": "building / factory / supermarket-scale",
    "High 8-C": "large building / skyscraper",
    "8-B": "city block",
    "8-A": "multiple city blocks",
    "Low 7-C": "small town → large town",
    "7-C": "small town → large town",
    "High 7-C": "small town → large town",
    "Low 7-B": "small city → city",
    "7-B": "small city → city",
    "7-A": "mountain → large mountain",
    "High 7-A": "mountain → large mountain",
    "6-C": "island → large island",
    "High 6-C": "island → large island",
    "Low 6-B": "small country → large country",
    "6-B": "small country → large country",
    "High 6-B": "small country → large country",
    "6-A": "continent → multiple continents",
    "High 6-A": "continent → multiple continents",
    "5-C": "moon → planet → large planet",
    "Low 5-B": "moon → planet → large planet",
    "5-B": "Planet-level",
    "5-A": "moon → planet → large planet",
    "Low 4-C": "star → solar system range",
    "4-C": "star → solar system range",
    "High 4-C": "star → solar system range",
    "4-B": "star → solar system range",
    "4-A": "star → solar system range",
    "3-C": "galaxy → universe-scale",
    "3-B": "galaxy → universe-scale",
    "3-A": "galaxy → universe-scale",
    "High 3-A": "galaxy → universe-scale",
    "Low 2-C": "multiple universes / timelines",
    "2-C": "multiple universes / timelines",
    "2-B": "multiple universes / timelines",
    "2-A": "multiple universes / timelines",
    "1-C": "dimensional / reality-framework scale",
    "1-B": "dimensional / reality-framework scale",
    "1-A": "dimensional / reality-framework scale",
    "0": "dimensional / reality-framework scale",
}


@dataclass(frozen=True)
class PublicPowerScale:
    damage_class: str
    footprint: str
    source_tier: str
    tiers: tuple[str, ...]


def canonical_tier(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip())
    if not normalized:
        return ""
    prefix = ""
    rest = normalized
    lower = normalized.casefold()
    if lower.startswith("high "):
        prefix = "High "
        rest = normalized[5:]
    elif lower.startswith("low "):
        prefix = "Low "
        rest = normalized[4:]
    return prefix + rest.upper()


def clean_public_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\{\{([^{}|]+)(?:\|[^{}]*)?\}\}", r"\1", text)
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", text)
    text = text.replace("{", "").replace("}", "").replace("[", "").replace("]", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip() or "n/a"


def extract_tier_tokens(value: Any) -> list[str]:
    text = clean_public_text(value)
    tiers = []
    seen = set()
    for match in TIER_PATTERN.finditer(text):
        tier = canonical_tier(match.group(0))
        if tier and tier not in seen:
            seen.add(tier)
            tiers.append(tier)
    return tiers


def join_unique(values: list[str]) -> str:
    seen = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    if not unique:
        return "Unknown"
    return " → ".join(unique)


def public_power_scale(raw_tier_text: Any) -> PublicPowerScale:
    tiers = extract_tier_tokens(raw_tier_text)
    damage_class = join_unique([TIER_DAMAGE_CLASS[tier] for tier in tiers if tier in TIER_DAMAGE_CLASS])
    footprint = join_unique([TIER_FOOTPRINT[tier] for tier in tiers if tier in TIER_FOOTPRINT])
    source_tier = " → ".join(tiers) if tiers else clean_public_text(raw_tier_text)
    if source_tier == "n/a":
        source_tier = "Unknown"
    return PublicPowerScale(
        damage_class=damage_class,
        footprint=footprint,
        source_tier=source_tier,
        tiers=tuple(tiers),
    )
