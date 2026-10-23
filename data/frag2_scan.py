#!/usr/bin/env python3
"""Part-2 prep scan (READ-ONLY): full text of the known grodd debris
items + scan of profiles/generated/** (live set) for the exact
new-shape patterns: item text containing 'Before making any changes',
or a bare 'Deviantart N' item."""
import glob
import re
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml


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


def item_text(i):
    return " ".join(
        str(i.get(k) or "") for k in ("name", "description", "text")
    ).strip()


print("== NAMED TARGETS (full item text)")
for rel in (
    "profiles/needs_review/comic/dc/gorilla-grodd.yaml",
    "profiles/needs_review/comic/dc/gorilla-grodd-dc-comics.yaml",
    "profiles/generated/comic/dc/gorilla-grodd-post-crisis.yaml",
    "profiles/generated/comic/dc/etrigan-dc-comics.yaml",
):
    try:
        prof = load("/app/" + rel)
    except Exception as exc:  # noqa: BLE001
        print(f"-- {rel}: LOAD FAIL {exc}")
        continue
    print(f"-- {rel}")
    for section, i in iter_items(prof):
        if section == "weaknesses":
            print(f"   [{section}] id={i.get('id')!r} name={str(i.get('name'))!r}")

print("\n== GENERATED SCAN")
BARE_LABEL = re.compile(r"(?i)^\s*deviant\s?art\s*\d*\s*[.…]*\s*$")
hits = 0
for path in sorted(glob.glob("/app/profiles/generated/**/*.yaml", recursive=True)):
    try:
        prof = load(path)
    except Exception:  # noqa: BLE001
        continue
    for section, i in iter_items(prof):
        text = item_text(i)
        if "Before making any changes" in text or BARE_LABEL.match(str(i.get("name") or "")):
            hits += 1
            rel = path.split("/app/")[-1]
            print(f"HIT {rel} [{section}] id={i.get('id')!r} name={str(i.get('name'))[:200]!r}")
print(f"total hits: {hits}")
