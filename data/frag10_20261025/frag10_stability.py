#!/usr/bin/env python3
"""Frag-10 stability re-read: profile-only invalid scan + battle_eligible count.
Writes stability.json."""
import json
from pathlib import Path

import yaml

PROFILES = Path("/app/profiles")
OUT = Path("/app/data/frag10_20261025/stability.json")
NON_PROFILES = {
    "example_character.yaml",
    "review_notes.yaml",
    "overrides/character_aliases.yaml",
    "overrides/preferred_profiles.yaml",
    "overrides/source_candidates.yaml",
    "overrides/source_registry.yaml",
}

invalid = []
eligible = 0
total = 0
for p in sorted(PROFILES.rglob("*.yaml")):
    if p.relative_to(PROFILES).as_posix() in NON_PROFILES:
        continue
    try:
        data = yaml.load(p.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:  # noqa: BLE001
        continue
    total += 1
    if data.get("battle_eligible") is True:
        eligible += 1
    gen = data.get("generation") or {}
    reasons = gen.get("ineligible_reasons")
    if data.get("battle_eligible") is not True and reasons in ([], None):
        invalid.append(str(p))

report = {"profiles_scanned": total, "battle_eligible": eligible,
          "invalid_count": len(invalid), "invalid": invalid}
OUT.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
