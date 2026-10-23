#!/usr/bin/env python3
"""Phase 3 gate-fail reverts: remove exactly the debris items/fields the
sample-50d merges added, per profile, wherever the profile now lives.
Everything else from the run stays. Prints a per-action verification."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io

EXPECTED = json.loads(Path("/app/data/recovery_sample50d_expected.json").read_text())

REMOVE = {
    "profiles/needs_review/comic/dc/beast-boy-dc-comics.yaml": [
        ("weaknesses", "weaknesses-none-notable"),
        ("abilities", "powers-and-abilities-resistance-to-extreme-temperatures-berserker-mode"),
    ],
    "profiles/needs_review/comic/dc/beast-boy-post-flashpoint.yaml": [
        ("weaknesses", "weaknesses-none-notable"),
        ("abilities", "powers-and-abilities-resistance-to-extreme-temperatures-berserker-mode"),
    ],
    "profiles/needs_review/comic/dc/beast-boy-post-crisis.yaml": [
        ("abilities", "powers-and-abilities-resistance-to-extreme-temperatures-berserk-mode"),
    ],
    "profiles/needs_review/comic/dc/beast-boy-rebirth.yaml": [
        ("abilities", "powers-and-abilities-resistance-to-extreme-temperatures-berserk-mode"),
    ],
    "profiles/needs_review/comic/dc/captain-atom-rebirth.yaml": [
        ("weaknesses", "weaknesses-space"),
        ("weaknesses", "weaknesses-energy"),
    ],
    "profiles/needs_review/comic/dc/big-barda-dc-comics.yaml": [
        ("abilities", "powers-and-abilities-gravity-manipulation-with-her-mega-rod-and"),
        ("abilities", "powers-and-abilities-and-healing-with-her-mother-box"),
        ("abilities", "powers-and-abilities-resistance-to-disease-manipulation"),
    ],
    "profiles/needs_review/comic/dc/circe.yaml": [
        ("abilities", "powers-and-abilities-and-astral-projection"),
    ],
    "profiles/needs_review/comic/dc/circe-dc-comics.yaml": [
        ("abilities", "powers-and-abilities-and-astral-projection"),
    ],
}
TIER_RESTORE = [
    "profiles/needs_review/comic/dc/beast-boy-post-crisis.yaml",
    "profiles/needs_review/comic/dc/beast-boy-rebirth.yaml",
]


def locate(rel: str) -> Path:
    path = Path(rel)
    if path.exists():
        return path
    gen = Path(rel.replace("profiles/needs_review/", "profiles/generated/"))
    if gen.exists():
        return gen
    raise FileNotFoundError(rel)


def items_of(profile, section):
    items = profile.get(section)
    if isinstance(items, dict):
        return items, True
    return items, False


actions = []
for rel, removals in REMOVE.items():
    path = locate(rel)
    profile = yaml_io.load_yaml(path)
    for section, id_prefix in removals:
        items, is_dict = items_of(profile, section)
        if items is None:
            actions.append(f"MISS {rel} [{section}] section absent")
            continue
        if is_dict:
            keys = [k for k, v in items.items()
                    if isinstance(v, dict) and str(v.get("id") or "").startswith(id_prefix)]
            for k in keys:
                del items[k]
                actions.append(f"REMOVED {rel} [{section}] id-prefix {id_prefix} (key {k})")
            if not keys:
                actions.append(f"MISS {rel} [{section}] no item with id-prefix {id_prefix}")
        else:
            kept = [i for i in items if not (isinstance(i, dict)
                    and str(i.get("id") or "").startswith(id_prefix))]
            removed = len(items) - len(kept)
            profile[section] = kept
            actions.append(f"REMOVED x{removed} {rel} [{section}] id-prefix {id_prefix}")
    yaml_io.write_yaml(path, profile)

for rel in TIER_RESTORE:
    path = locate(rel)
    profile = yaml_io.load_yaml(path)
    before_tier = (EXPECTED[rel].get("power_scale") or {}).get("tier")
    current = (profile.get("power_scale") or {}).get("tier")
    profile.setdefault("power_scale", {})["tier"] = before_tier
    yaml_io.write_yaml(path, profile)
    actions.append(f"TIER RESTORED {rel}: {str((current or {}).get('text'))!r} -> "
                   f"{str((before_tier or {}).get('text'))!r}")

for a in actions:
    print(a)
