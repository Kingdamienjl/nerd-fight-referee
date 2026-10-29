#!/usr/bin/env python3
"""Frag-9 gate-50o manual-review manifest: every NEW item / stat
(before empty -> after set) with FULL text, grouped by profile.
Read-only."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

expected = json.loads(
    Path("/app/data/recovery_sample50o_expected.json").read_text())
actual = json.loads(
    Path("/app/data/recovery_sample50o_actual.json").read_text())
sample = json.loads(
    Path("/app/data/recovery_sample50o_list.json").read_text())["sample"]
progress = json.loads(
    Path("/app/data/recovery_progress.json").read_text())


def item_key(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or "") or ar.normalized_identity_text(
        item.get("name") or item.get("label") or "")


def stat_text(field):
    if isinstance(field, dict):
        return str(field.get("text") or "")
    return str(field or "")


n_profiles = 0
n_items = 0
n_stats = 0
for rel in sample:
    entry = progress.get(rel) or {}
    if not entry.get("recovered_fields"):
        continue
    n_profiles += 1
    before, after = expected[rel], actual[rel]
    print(f"\n##### {rel}")
    print(f"  recovered_fields={entry.get('recovered_fields')}")
    for fname in ("abilities", "weaknesses", "equipment"):
        bmap = {item_key(i): i for i in (before.get(fname) or [])
                if isinstance(i, dict)}
        for item in after.get(fname) or []:
            if not isinstance(item, dict):
                continue
            if item_key(item) not in bmap:
                n_items += 1
                print(f"  NEW [{fname}] name={item.get('name')!r}")
                print(f"      desc={str(item.get('description') or '')!r}")
    for fname in ("attack_potency", "speed", "durability", "stamina",
                  "range", "intelligence", "lifting_strength",
                  "striking_strength", "tier"):
        b = (before.get("power_scale") or {}).get(fname)
        a = (after.get("power_scale") or {}).get(fname)
        if not stat_text(b) and stat_text(a):
            n_stats += 1
            print(f"  NEW [stat:{fname}] {stat_text(a)!r}")

print(f"\nTOTAL: {n_profiles} recovered profiles, {n_items} new items, "
      f"{n_stats} new stats")
