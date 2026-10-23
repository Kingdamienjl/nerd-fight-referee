#!/usr/bin/env python3
"""Mop-up scan: every generated item whose NAME clean_item_tails
would change (tail strip or tail-only reject), regardless of the
footer phrase. Applies the same decide() rules as frag2_clean.py
and performs the actions. Prints each action."""
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import glob

from battlebot.profiles import yaml_io
from battlebot.review import auto_repair as ar

BARE_LABEL = re.compile(r"(?i)^\s*deviant\s?art\s*\d*\s*[.…]*\s*$")
BUNDLE_PREFIX = "please read and follow the Power-scaling Rules"
SECTION_OF = {
    "abilities": "powers_and_abilities",
    "weaknesses": "weaknesses",
    "equipment": "standard_equipment",
}


def decide(section, name):
    if name.startswith(BUNDLE_PREFIX):
        return "REMOVE", "footer_bundle", ""
    if BARE_LABEL.match(name):
        return "REMOVE", "bare_label", ""
    cleaned, tail_reasons = ar.clean_item_tails(name)
    if not tail_reasons:
        return None, "", ""
    if not cleaned:
        return "REMOVE", f"tail_only:{tail_reasons}", ""
    if "Before making any changes" in name:
        reasons = list(ar.placeholder_item_reasons(cleaned))
        for reason in ar.fragment_item_reasons(
            cleaned, section=SECTION_OF[section]
        ):
            if reason not in reasons:
                reasons.append(reason)
        if reasons:
            return "REMOVE", f"cleaned_still_debris:{reasons}", ""
    return "STRIP", f"{tail_reasons}", cleaned


actions = []
for path in sorted(glob.glob("/app/profiles/generated/**/*.yaml", recursive=True)):
    rel = path.split("/app/")[-1]
    profile = yaml_io.load_yaml(Path(path))
    changed = False
    for section in ("abilities", "weaknesses", "equipment"):
        items = profile.get(section)
        is_dict = isinstance(items, dict)
        seq = list(items.values()) if is_dict else list(items or [])
        for item in seq:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            bucket, detail, cleaned = decide(section, name)
            if bucket is None:
                continue
            if bucket == "REMOVE":
                if is_dict:
                    for key in [
                        k for k, v in items.items()
                        if isinstance(v, dict) and v.get("id") == item.get("id")
                    ]:
                        del items[key]
                else:
                    profile[section] = [
                        i for i in profile[section]
                        if not (isinstance(i, dict) and i.get("id") == item.get("id"))
                    ]
                changed = True
                actions.append(
                    f"REMOVE {rel} [{section}] id={item.get('id')} "
                    f"({detail}) name={name[:90]!r}"
                )
            else:
                item["name"] = cleaned
                changed = True
                actions.append(
                    f"STRIP {rel} [{section}] id={item.get('id')} "
                    f"({detail}) -> {cleaned[:90]!r}"
                )
    if changed:
        yaml_io.write_yaml(Path(path), profile)

for line in actions:
    print(line)
print(f"total actions: {len(actions)}")
