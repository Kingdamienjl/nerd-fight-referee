"""Curated character variant metadata.

Variants are explicit forms, armor, continuity versions, or game/anime versions with
different likely combat profiles. This module intentionally does not generate arbitrary
suffixes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VariantSeed:
    category: str
    franchise: str
    parent_name: str
    variant_name: str
    variant_type: str
    aliases: str = ""
    battle_notes: str = ""

    @property
    def name(self) -> str:
        return f"{self.parent_name} ({self.variant_name})"


CURATED_VARIANTS: tuple[VariantSeed, ...] = (
    VariantSeed("comic", "Marvel", "Iron Man", "Hulkbuster", "armor", "Tony Stark|Hulkbuster"),
    VariantSeed("comic", "Marvel", "Iron Man", "Extremis Armor", "armor", "Tony Stark|Extremis"),
    VariantSeed("comic", "Marvel", "Iron Man", "Bleeding Edge", "armor", "Tony Stark|Bleeding Edge Armor"),
    VariantSeed("comic", "Marvel", "Spider-Man", "Symbiote Suit", "equipment", "Peter Parker|Black Suit"),
    VariantSeed("comic", "Marvel", "Thor", "Rune King Thor", "form"),
    VariantSeed("comic", "Marvel", "Hulk", "World Breaker Hulk", "form", "Bruce Banner"),
    VariantSeed("comic", "Marvel", "Jean Grey", "Phoenix", "form", "Phoenix Force"),
    VariantSeed("comic", "Marvel", "Ghost Rider", "Zarathos", "form", "Johnny Blaze"),
    VariantSeed("comic", "DC", "Batman", "Hellbat Armor", "armor", "Bruce Wayne|Hellbat"),
    VariantSeed("comic", "DC", "Batman", "Final Batsuit", "armor", "Bruce Wayne"),
    VariantSeed("comic", "DC", "Superman", "Post-Crisis", "continuity", "Clark Kent"),
    VariantSeed("comic", "DC", "Superman", "Prime Earth", "continuity", "Clark Kent"),
    VariantSeed("comic", "DC", "Superman", "All-Star", "continuity", "Clark Kent"),
    VariantSeed("comic", "DC", "Wonder Woman", "Post-Crisis", "continuity", "Diana Prince"),
    VariantSeed("comic", "DC", "The Flash", "Wally West", "continuity", "Flash|Wally West"),
    VariantSeed("comic", "DC", "The Flash", "Barry Allen", "continuity", "Flash|Barry Allen"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Kaioken", "form", "Goku|Kakarot"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Super Saiyan", "form", "Goku|Kakarot|SSJ"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Super Saiyan 2", "form", "Goku|Kakarot|SSJ2"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Super Saiyan 3", "form", "Goku|Kakarot|SSJ3"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Super Saiyan 4", "form", "Goku|Kakarot|SSJ4"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Super Saiyan God", "form", "Goku|Kakarot|SSG"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Super Saiyan Blue", "form", "Goku|Kakarot|SSB"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Super Saiyan Blue Kaioken", "form", "Goku|Kakarot|SSB Kaioken"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Ultra Instinct Sign", "form", "Goku|Kakarot|UI Sign"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Mastered Ultra Instinct", "form", "Goku|Kakarot|MUI"),
    VariantSeed("anime", "Dragon Ball", "Son Goku", "Ultra Instinct", "form", "Goku|Kakarot|UI"),

    VariantSeed("anime", "Dragon Ball", "Vegeta", "Super Saiyan", "form", "SSJ Vegeta"),
    VariantSeed("anime", "Dragon Ball", "Vegeta", "Super Saiyan 2", "form", "SSJ2 Vegeta"),
    VariantSeed("anime", "Dragon Ball", "Vegeta", "Majin", "form", "Majin Vegeta"),
    VariantSeed("anime", "Dragon Ball", "Vegeta", "Super Saiyan God", "form", "SSG Vegeta"),
    VariantSeed("anime", "Dragon Ball", "Vegeta", "Super Saiyan Blue", "form", "SSB Vegeta"),
    VariantSeed("anime", "Dragon Ball", "Vegeta", "Super Saiyan Blue Evolved", "form", "Blue Evolution Vegeta"),
    VariantSeed("anime", "Dragon Ball", "Vegeta", "Ultra Ego", "form"),

    VariantSeed("anime", "Dragon Ball", "Frieza", "First Form", "form"),
    VariantSeed("anime", "Dragon Ball", "Frieza", "Second Form", "form"),
    VariantSeed("anime", "Dragon Ball", "Frieza", "Third Form", "form"),
    VariantSeed("anime", "Dragon Ball", "Frieza", "Final Form", "form"),
    VariantSeed("anime", "Dragon Ball", "Frieza", "100%", "form", "Full Power Frieza"),
    VariantSeed("anime", "Dragon Ball", "Frieza", "Mecha", "form", "Mecha Frieza"),
    VariantSeed("anime", "Dragon Ball", "Frieza", "Golden", "form", "Golden Frieza"),
    VariantSeed("anime", "Dragon Ball", "Frieza", "Black", "form", "Black Frieza"),

    VariantSeed("anime", "Dragon Ball", "Gohan", "Super Saiyan", "form"),
    VariantSeed("anime", "Dragon Ball", "Gohan", "Super Saiyan 2", "form"),
    VariantSeed("anime", "Dragon Ball", "Gohan", "Ultimate", "form", "Mystic Gohan|Ultimate Gohan"),
    VariantSeed("anime", "Dragon Ball", "Gohan", "Beast", "form", "Beast Gohan"),

    VariantSeed("anime", "Dragon Ball", "Cell", "Imperfect", "form"),
    VariantSeed("anime", "Dragon Ball", "Cell", "Semi-Perfect", "form"),
    VariantSeed("anime", "Dragon Ball", "Cell", "Perfect", "form"),
    VariantSeed("anime", "Dragon Ball", "Cell", "Super Perfect", "form"),

    VariantSeed("anime", "Dragon Ball", "Majin Buu", "Innocent", "form", "Fat Buu"),
    VariantSeed("anime", "Dragon Ball", "Majin Buu", "Evil", "form"),
    VariantSeed("anime", "Dragon Ball", "Majin Buu", "Super Buu", "form"),
    VariantSeed("anime", "Dragon Ball", "Majin Buu", "Kid Buu", "form"),
    VariantSeed("anime", "Naruto", "Naruto Uzumaki", "Six Paths Sage Mode", "form", "Naruto"),
    VariantSeed("anime", "Naruto", "Sasuke Uchiha", "Rinnegan", "form", "Sasuke"),
    VariantSeed("anime", "Bleach", "Ichigo Kurosaki", "True Bankai", "form", "Ichigo"),
    VariantSeed("anime", "One Piece", "Luffy", "Gear 5", "form", "Monkey D. Luffy|Nika"),
    VariantSeed("anime", "Sailor Moon", "Sailor Moon", "Eternal", "form", "Usagi Tsukino|Eternal Sailor Moon"),
    VariantSeed("game", "Devil May Cry", "Dante", "Sin Devil Trigger", "form"),
    VariantSeed("game", "Devil May Cry", "Vergil", "Sin Devil Trigger", "form"),
    VariantSeed("game", "Kingdom Hearts", "Sora", "Kingdom Hearts III", "version", "Sora KH3"),
    VariantSeed("game", "Final Fantasy", "Cloud Strife", "Advent Children", "version", "Cloud"),
    VariantSeed("game", "The Legend of Zelda", "Link", "Breath of the Wild", "version", "BOTW Link"),
    VariantSeed("game", "Metroid", "Samus Aran", "Varia Suit", "equipment", "Samus|Varia"),
    VariantSeed("game", "Doom", "Doom Slayer", "Praetor Suit", "equipment", "Doomguy"),
    VariantSeed("game", "God of War", "Kratos", "Norse Era", "version"),
)


VARIANT_BY_NAME = {seed.name.casefold(): seed for seed in CURATED_VARIANTS}


def variant_seed_for_name(name: str) -> VariantSeed | None:
    return VARIANT_BY_NAME.get(name.casefold())


def split_variant_name(name: str) -> tuple[str, str | None]:
    match = re.fullmatch(r"\s*(.+?)\s*\(([^()]+)\)\s*", name)
    if not match:
        return name.strip(), None
    return match.group(1).strip(), match.group(2).strip()


def variant_metadata(name: str, character_id: str = "") -> dict[str, Any]:
    seed = variant_seed_for_name(name)
    if seed:
        parent_id = "-".join(
            part
            for part in re.sub(r"[^a-z0-9]+", "-", f"{seed.category}-{seed.franchise}-{seed.parent_name}".casefold()).split("-")
            if part
        )
        return {
            "parent_character_id": parent_id,
            "variant_name": seed.variant_name,
            "variant_type": seed.variant_type,
            "default_variant": False,
            "battle_notes": seed.battle_notes,
        }
    parent, variant = split_variant_name(name)
    if variant:
        return {
            "parent_character_id": "",
            "variant_name": variant,
            "variant_type": "version",
            "default_variant": False,
            "battle_notes": "Uncurated variant; requires source-backed validation before battle use.",
        }
    return {
        "parent_character_id": character_id,
        "variant_name": None,
        "variant_type": None,
        "default_variant": True,
        "battle_notes": "Default/base battle profile.",
    }


def variant_search_queries(name: str, franchise: str, aliases: list[str] | None = None) -> list[str]:
    parent, variant = split_variant_name(name)
    queries = [name]
    if variant:
        queries.extend([f"{parent} {variant}", f"{parent} {variant} {franchise}".strip()])
    if franchise:
        queries.extend([f"{name} {franchise}", f"{name} ({franchise})"])
    queries.extend(aliases or [])
    seen = set()
    unique = []
    for query in queries:
        cleaned = query.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return unique
