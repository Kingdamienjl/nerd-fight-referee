#!/usr/bin/env python3
"""Restore captain-atom-rebirth's substantive 'Energy over matter'
weakness item (removed by an over-broad id prefix) from the post-run
actual snapshot, at its original position. Verify final id set."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io

REL = "profiles/needs_review/comic/dc/captain-atom-rebirth.yaml"
actual = json.loads(Path("/app/data/recovery_sample50d_actual.json").read_text())
snap_items = actual[REL].get("weaknesses")
if isinstance(snap_items, dict):
    snap_items = list(snap_items.values())
snap_ids = [str(i.get("id")) for i in snap_items if isinstance(i, dict)]
target = next(i for i in snap_items
              if str(i.get("id")).startswith("weaknesses-energy-over-matter"))

path = Path(REL)
profile = yaml_io.load_yaml(path)
items = profile.get("weaknesses")
is_dict = isinstance(items, dict)
if is_dict:
    items = list(items.values())
current_ids = [str(i.get("id")) for i in items if isinstance(i, dict)]
assert str(target.get("id")) not in current_ids, "already present"

snap_index = snap_ids.index(str(target.get("id")))
# position = number of surviving snapshot items that preceded it
surviving_before = [i for i in snap_ids[:snap_index] if i in current_ids]
insert_at = len(surviving_before)
items.insert(insert_at, target)
if is_dict:
    profile["weaknesses"] = {str(i.get("id")): i for i in items}
else:
    profile["weaknesses"] = items
yaml_io.write_yaml(path, profile)

final_ids = [str(i.get("id")) for i in items if isinstance(i, dict)]
expected_final = [i for i in snap_ids
                  if i not in ("weaknesses-space", "weaknesses-energy")]
print("restored:", target.get("id"))
print("final matches snapshot-minus-debris:", final_ids == expected_final)
print("final weakness count:", len(final_ids))
