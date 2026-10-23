#!/usr/bin/env python3
"""Part-2 cleanup classification (READ-ONLY). For every item in
profiles/generated/** whose name/description/text contains
'Before making any changes' or that is a bare version-key label,
classify by the Part 1 screen semantics:
  REMOVE  - item name is only debris (clean_item_tails -> '',
            or the footer bundle prefix, or cleaned text still
            fails the item screens)
  STRIP   - name carries a substantive clause + tail; cleaned name
            passes ALL item screens -> rename item to cleaned text
  REPORT  - pattern only in description/text, name clean -> no touch
Prints one line per hit with bucket + details, plus bucket counts.
"""
import glob
import json
import re
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

BARE_LABEL = re.compile(r"(?i)^\s*deviant\s?art\s*\d*\s*[.…]*\s*$")
BUNDLE_PREFIX = "please read and follow the Power-scaling Rules"


def load(path):
    with open(path) as handle:
        return yaml.load(handle, Loader=yaml.CSafeLoader) or {}


def iter_items(prof):
    for section in ("abilities", "weaknesses", "equipment"):
        items = prof.get(section)
        if isinstance(items, dict):
            items = list(items.values())
        for i in items or []:
            if isinstance(i, dict):
                yield section, i


def classify(section, item):
    name = str(item.get("name") or "")
    other = " ".join(
        str(item.get(k) or "") for k in ("description", "text")
    ).strip()
    phrase_in_name = "Before making any changes" in name
    phrase_in_other = "Before making any changes" in other
    label_in_other = bool(
        re.search(r"(?i)deviant\s?art|amino\s+apps|respect\s+threads", other)
    )
    if name.startswith(BUNDLE_PREFIX):
        return "REMOVE", "footer_bundle", name
    if BARE_LABEL.match(name):
        return "REMOVE", "bare_label", name
    if not phrase_in_name:
        if phrase_in_other or label_in_other:
            return "REPORT", "pattern_in_description_only", name
        return None, "", name
    cleaned, tail_reasons = ar.clean_item_tails(name)
    if not cleaned:
        return "REMOVE", f"note_only:{tail_reasons}", name
    screen_reasons = list(ar.placeholder_item_reasons(cleaned))
    for reason in ar.fragment_item_reasons(
        cleaned, section=ar_section(section)
    ):
        if reason not in screen_reasons:
            screen_reasons.append(reason)
    if screen_reasons:
        return "REMOVE", f"cleaned_still_debris:{screen_reasons}", name
    return "STRIP", f"{tail_reasons} -> {cleaned!r}", name


def ar_section(section):
    return {
        "abilities": "powers_and_abilities",
        "weaknesses": "weaknesses",
        "equipment": "standard_equipment",
    }[section]


buckets = {"REMOVE": [], "STRIP": [], "REPORT": []}
for path in sorted(glob.glob("/app/profiles/generated/**/*.yaml", recursive=True)):
    try:
        prof = load(path)
    except Exception:  # noqa: BLE001
        continue
    rel = path.split("/app/")[-1]
    for section, item in iter_items(prof):
        text = " ".join(
            str(item.get(k) or "") for k in ("name", "description", "text")
        )
        if (
            "Before making any changes" not in text
            and not BARE_LABEL.match(str(item.get("name") or ""))
            and not str(item.get("name") or "").startswith(BUNDLE_PREFIX)
        ):
            continue
        bucket, detail, name = classify(section, item)
        if bucket:
            buckets[bucket].append(
                {
                    "profile": rel,
                    "section": section,
                    "id": item.get("id"),
                    "detail": detail,
                    "name": name,
                }
            )

for bucket in ("REMOVE", "STRIP", "REPORT"):
    print(f"== {bucket}: {len(buckets[bucket])}")
    for hit in buckets[bucket]:
        print(json.dumps(hit, ensure_ascii=False))
