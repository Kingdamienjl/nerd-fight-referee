#!/usr/bin/env python3
"""Part-2 live-debris cleanup. Applies the classification rules
FRESH at clean time to: (a) every candidate item from
frag2_classify.out (REMOVE/STRIP lines), (b) the footer-bundle
item in the two named needs_review grodd profiles.
REMOVE deletes the item; STRIP renames the item to its cleaned
text (item id kept stable). Prints one line per action. DB rows
are refreshed by the caller via import_generated_profiles.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io
from battlebot.review import auto_repair as ar

BARE_LABEL = re.compile(r"(?i)^\s*deviant\s?art\s*\d*\s*[.…]*\s*$")
BUNDLE_PREFIX = "please read and follow the Power-scaling Rules"
SECTION_OF = {
    "abilities": "powers_and_abilities",
    "weaknesses": "weaknesses",
    "equipment": "standard_equipment",
}
NAMED = (
    "profiles/needs_review/comic/dc/gorilla-grodd.yaml",
    "profiles/needs_review/comic/dc/gorilla-grodd-dc-comics.yaml",
)


def decide(section, name):
    """Return ('REMOVE'|'STRIP'|None, detail, cleaned)."""
    if name.startswith(BUNDLE_PREFIX):
        return "REMOVE", "footer_bundle", ""
    if BARE_LABEL.match(name):
        return "REMOVE", "bare_label", ""
    if "Before making any changes" not in name:
        _cleaned, tail_reasons = ar.clean_item_tails(name)
        if tail_reasons and not _cleaned:
            return "REMOVE", f"tail_only:{tail_reasons}", ""
        if tail_reasons:
            return "STRIP", f"{tail_reasons}", _cleaned
        return None, "", ""
    cleaned, tail_reasons = ar.clean_item_tails(name)
    if not cleaned:
        return "REMOVE", f"note_only:{tail_reasons}", ""
    reasons = list(ar.placeholder_item_reasons(cleaned))
    for reason in ar.fragment_item_reasons(cleaned, section=SECTION_OF[section]):
        if reason not in reasons:
            reasons.append(reason)
    if reasons:
        return "REMOVE", f"cleaned_still_debris:{reasons}", ""
    return "STRIP", f"{tail_reasons}", cleaned


candidates = {}  # rel -> set of item ids from classify (REMOVE/STRIP)
for line in Path("/app/data/frag2_classify.out").read_text().splitlines():
    if not line.startswith("{"):
        continue
    hit = json.loads(line)
    candidates.setdefault(hit["profile"], set()).add(hit["id"])
for rel in NAMED:
    candidates.setdefault(rel, set())

actions = []
for rel, ids in sorted(candidates.items()):
    path = Path(rel)
    if not path.exists():
        actions.append(f"MISS {rel} (file gone)")
        continue
    profile = yaml_io.load_yaml(path)
    changed = False
    for section in ("abilities", "weaknesses", "equipment"):
        items = profile.get(section)
        is_dict = isinstance(items, dict)
        seq = list(items.values()) if is_dict else list(items or [])
        for item in seq:
            if not isinstance(item, dict):
                continue
            if rel not in NAMED and str(item.get("id")) not in ids:
                continue
            name = str(item.get("name") or "")
            bucket, detail, cleaned = decide(section, name)
            if bucket is None:
                if rel in NAMED:
                    continue
                actions.append(
                    f"SKIP-CLEAN {rel} [{section}] id={item.get('id')} "
                    f"(no longer matches patterns)"
                )
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
            else:  # STRIP
                item["name"] = cleaned
                changed = True
                actions.append(
                    f"STRIP {rel} [{section}] id={item.get('id')} "
                    f"({detail}) -> {cleaned[:90]!r}"
                )
    if changed:
        yaml_io.write_yaml(path, profile)

for line in actions:
    print(line)
print(f"total actions: {len(actions)}")
