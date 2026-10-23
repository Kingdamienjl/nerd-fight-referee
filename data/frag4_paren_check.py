#!/usr/bin/env python3
"""Frag-4 50h audit follow-up: paren forensics for flagged items +
full new-item listing for manual review (name, name_len, desc
paren balance, desc head)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

expected = json.loads(Path("/app/data/recovery_sample50h_expected.json").read_text())
actual = json.loads(Path("/app/data/recovery_sample50h_actual.json").read_text())
sample = json.loads(Path("/app/data/recovery_sample50h_list.json").read_text())["sample"]
progress = json.loads(Path("/app/data/recovery_progress.json").read_text())


def item_key(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or "") or ar.normalized_identity_text(
        item.get("name") or item.get("label") or "")


for rel in sample:
    entry = progress.get(rel) or {}
    if not entry.get("recovered_fields"):
        continue
    before, after = expected[rel], actual[rel]
    print(f"== {rel} recovered={entry.get('recovered_fields')}")
    b_ps, a_ps = before.get("power_scale") or {}, after.get("power_scale") or {}
    if isinstance(a_ps, dict):
        for field, a_item in a_ps.items():
            if not isinstance(a_item, dict):
                continue
            a_text = str(a_item.get("text") or "")
            b_item = b_ps.get(field) if isinstance(b_ps, dict) else None
            b_text = str((b_item or {}).get("text") or "") if isinstance(b_item, dict) else ""
            if a_text and a_text != b_text:
                print(f"   STAT {field}: {a_text[:130]!r}")
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
            name = str(item.get("name") or "")
            desc = str(item.get("description") or "")
            bal = desc.count("(") - desc.count(")")
            nbal = name.count("(") - name.count(")")
            flag = ""
            if nbal != 0:
                flag = f"  <-- NAME paren delta {nbal:+d}, name_len={len(name)}, desc paren delta {bal:+d}"
            print(f"   ITEM [{section}] {name[:100]!r} desc={desc[:80]!r}{flag}")
