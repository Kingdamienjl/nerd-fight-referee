#!/usr/bin/env python3
"""Frag-7 refined calibration: run the REAL new screens over every
stored weakness item name in /app/profiles and report:
  - name_only_technique_in_weaknesses hits (raw + distinct + samples)
  - explicit_none placeholder hits (raw + distinct + samples)
  - the excluded weapon-noun class size (Title-Case bare names ending
    in a weapon/object noun -- deliberately NOT screened)
Read-only."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

WEAPON_ENDINGS = {
    "blade", "blades", "sword", "swords", "spear", "spears", "whip",
    "whips", "arrow", "arrows", "cannon", "bomb", "bombs", "fang",
    "fangs", "claw", "claws", "orb", "wave", "waves", "ray", "rays",
    "bolt", "bolts", "axe", "hammer", "hammers", "staff", "staves",
    "shield", "shields", "gun", "guns", "lance", "lances", "dagger",
    "daggers", "scythe", "whip", "chain", "chains", "horn", "horns",
    "tooth", "teeth", "sting", "stinger", "tail", "tails", "wing",
    "wings", "eye", "eyes", "hand", "hands",
}


def titlecase_bare_name(name: str) -> bool:
    tokens = name.strip().rstrip(".:!").split()
    if not 2 <= len(tokens) <= 5:
        return False
    for token in tokens:
        core = token.strip(".,:;'\"()")
        if not core:
            return False
        if core[:1].isupper() or core.casefold() in ar._NAME_FORM_CONNECTORS or core.isdigit():
            continue
        return False
    return True


profiles = 0
items = 0
nameonly = Counter()
nameonly_examples = {}
none_hits = Counter()
none_examples = {}
weapon_class = Counter()

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        with path.open() as handle:
            prof = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    profiles += 1
    weak = prof.get("weaknesses")
    if isinstance(weak, dict):
        weak = list(weak.values())
    for item in weak or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        items += 1
        reasons = ar.fragment_item_reasons(name, section="weaknesses")
        if "name_only_technique_in_weaknesses" in reasons:
            key = name.casefold()
            nameonly[key] += 1
            nameonly_examples.setdefault(key, str(path))
        preasons = ar.placeholder_item_reasons(name)
        if "explicit_none" in preasons:
            key = name.casefold()
            none_hits[key] += 1
            none_examples.setdefault(key, str(path))
        if titlecase_bare_name(name):
            last = "".join(ch for ch in name.split()[-1].casefold() if ch.isalpha())
            if last in WEAPON_ENDINGS:
                weapon_class[name.casefold()] += 1

print(f"profiles_scanned={profiles} weakness_items={items}")
print(f"\n== NAME-ONLY TECHNIQUE (final rule): {sum(nameonly.values())} raw, {len(nameonly)} distinct")
for name, count in nameonly.most_common(60):
    print(f"   {count:4d}  {name!r}  e.g. {nameonly_examples[name]}")
print(f"\n== EXPLICIT-NONE pieces (final rule): {sum(none_hits.values())} raw, {len(none_hits)} distinct")
for name, count in none_hits.most_common(30):
    print(f"   {count:4d}  {name[:70]!r}  e.g. {none_examples[name]}")
print(f"\n== EXCLUDED weapon-noun Title-Case bare names: {sum(weapon_class.values())} raw, {len(weapon_class)} distinct")
for name, count in weapon_class.most_common(25):
    print(f"   {count:4d}  {name!r}")
