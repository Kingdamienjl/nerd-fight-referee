#!/usr/bin/env python3
"""Targeted scan: all NEW cohort merges (items + stats) whose text starts
with a conjunction (and/but/yet/so/nor) -- the long-fragment shape that
escapes the <=8-word conjunction_orphan cap. Prints full text."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

expected = json.loads(Path("/app/data/recovery_cohort11_expected.json").read_text())
actual = json.loads(Path("/app/data/recovery_cohort11_actual.json").read_text())
todo = json.loads(Path("/app/data/recovery_cohort11_list.json").read_text())["todo"]
progress = json.loads(Path("/app/data/recovery_progress.json").read_text())
CONJ_RE = re.compile(r"^(and|but|yet|so|nor)\b", re.I)

def item_key(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or "") or ar.normalized_identity_text(
        item.get("name") or item.get("label") or "")

hits = []
for rel in todo:
    entry = progress.get(rel) or {}
    if not entry.get("recovered_fields"):
        continue
    before, after = expected[rel], actual[rel]
    for section in ("abilities", "weaknesses", "equipment"):
        b_items = before.get(section)
        a_items = after.get(section)
        if isinstance(b_items, dict):
            b_items = list(b_items.values())
        if isinstance(a_items, dict):
            a_items = list(a_items.values())
        b_keys = {item_key(i) for i in b_items or [] if isinstance(i, dict)}
        for item in a_items or []:
            if not isinstance(item, dict) or item_key(item) in b_keys:
                continue
            for which, text in (("name", item.get("name")), ("desc", item.get("description"))):
                text = str(text or "")
                if CONJ_RE.match(text.strip()):
                    hits.append((rel, section, which, text))
                    break
    b_ps = before.get("power_scale") or {}
    a_ps = after.get("power_scale") or {}
    if isinstance(a_ps, dict):
        for field, a_item in a_ps.items():
            if not isinstance(a_item, dict):
                continue
            a_text = str(a_item.get("text") or "")
            b_item = b_ps.get(field) if isinstance(b_ps, dict) else None
            b_text = str((b_item or {}).get("text") or "") if isinstance(b_item, dict) else ""
            if not a_text or a_text == b_text:
                continue
            if CONJ_RE.match(a_text.strip()):
                hits.append((rel, f"stat:{field}", "text", a_text))
print(f"conj_led_new_merges={len(hits)}")
for rel, section, which, text in hits:
    print(f"--- {rel} [{section}] ({which}) words={len(text.split())}")
    print(f"    {text[:400]!r}")
print("ANDSCAN DONE")
