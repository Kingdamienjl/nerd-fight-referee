#!/usr/bin/env python3
"""Frag-3 re-gate 50g FAIL reverts (field/item-level, verified):
  - harley-quinn-post-flashpoint: remove the ONE glued tab-key
    composite ability item; the 5 Black Lantern abilities are
    audited-good and stay.
  - midnighter x3: restore power_scale.tier to the pre-run snapshot
    value (was empty; the run merged a bare 'At least' qualifier).
  - remove the 4 profiles' recovery progress keys (re-eligible).
Everything else from the sample stays."""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io

EXPECTED = json.loads(Path("/app/data/recovery_sample50g_expected.json").read_text())
COMPOSITE = "Base Hax Hammer Harleen Hax AoR Harley Hax Death Manipulation"
HARLEY = "profiles/needs_review/comic/dc/harley-quinn-post-flashpoint.yaml"
MIDNIGHTERS = (
    "profiles/needs_review/comic/dc/midnighter-dc-comics.yaml",
    "profiles/needs_review/comic/dc/midnighter-post-crisis.yaml",
    "profiles/needs_review/comic/dc/midnighter-rebirth.yaml",
)

actions = []

# --- harley: item-level revert ---
path = Path("/app") / HARLEY
profile = yaml_io.load_yaml(path)
abilities = profile.get("abilities")
is_dict = isinstance(abilities, dict)
seq = list(abilities.values()) if is_dict else list(abilities or [])
removed = 0
for item in seq:
    if isinstance(item, dict) and str(item.get("name") or "") == COMPOSITE:
        if is_dict:
            for key in [
                k for k, v in abilities.items()
                if isinstance(v, dict) and v.get("id") == item.get("id")
            ]:
                del abilities[key]
        else:
            profile["abilities"] = [
                i for i in profile["abilities"]
                if not (isinstance(i, dict) and i.get("id") == item.get("id"))
            ]
        removed += 1
        actions.append(f"REMOVE-ITEM {HARLEY} id={item.get('id')} name={COMPOSITE[:60]!r}")
assert removed == 1, f"harley composite removed={removed}"
yaml_io.write_yaml(path, profile)

# --- midnighter x3: tier field restore ---
for rel in MIDNIGHTERS:
    path = Path("/app") / rel
    profile = yaml_io.load_yaml(path)
    expected_tier = copy.deepcopy(
        (EXPECTED[rel].get("power_scale") or {}).get("tier")
    )
    current = (profile.get("power_scale") or {}).get("tier") or {}
    assert str(current.get("text") or "") == "At least", (rel, current)
    if expected_tier is None:
        profile["power_scale"]["tier"] = {
            "text": "", "source_ids": [], "confidence": 0.0,
        }
    else:
        profile["power_scale"]["tier"] = expected_tier
    yaml_io.write_yaml(path, profile)
    actions.append(
        f"RESTORE-FIELD {rel} power_scale.tier 'At least' -> {expected_tier!r}"
    )

# --- progress keys ---
progress_path = Path("/app/data/recovery_progress.json")
progress = json.loads(progress_path.read_text())
for rel in (HARLEY, *MIDNIGHTERS):
    if rel in progress:
        del progress[rel]
        actions.append(f"PROGRESS-KEY-REMOVED {rel}")
tmp = progress_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(progress, indent=1))
tmp.replace(progress_path)

# --- verify ---
profile = yaml_io.load_yaml(Path("/app") / HARLEY)
names = [
    str(i.get("name") or "")
    for i in (profile.get("abilities") or [])
    if isinstance(i, dict)
]
assert COMPOSITE not in names, "composite still present"
assert len(names) >= 5, names
actions.append(f"VERIFY harley abilities_now={len(names)} composite_absent=True")
for rel in MIDNIGHTERS:
    profile = yaml_io.load_yaml(Path("/app") / rel)
    tier_text = str(((profile.get("power_scale") or {}).get("tier") or {}).get("text") or "")
    assert tier_text != "At least", rel
    actions.append(f"VERIFY {rel} tier_now={tier_text!r}")
progress = json.loads(progress_path.read_text())
assert all(rel not in progress for rel in (HARLEY, *MIDNIGHTERS))
actions.append("VERIFY progress keys absent for all 4")

for line in actions:
    print(line)
print(f"total actions: {len(actions)}")
