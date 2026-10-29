#!/usr/bin/env python3
"""Print FULL text of every audit-flagged merge (cohort) for manual review.
Reproduces the cohort audit's flagged items with name+description, so a
human can adjudicate each one instead of trusting the reason label."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

expected = json.loads(Path("/app/data/recovery_cohort11_expected.json").read_text())
actual = json.loads(Path("/app/data/recovery_cohort11_actual.json").read_text())
todo = json.loads(Path("/app/data/recovery_cohort11_list.json").read_text())["todo"]
progress = json.loads(Path("/app/data/recovery_progress.json").read_text())
SECTION_OF_FIELD = {"abilities": "powers_and_abilities", "weaknesses": "weaknesses", "equipment": "standard_equipment"}

def item_key(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or "") or ar.normalized_identity_text(
        item.get("name") or item.get("label") or "")

n = 0
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
            reasons = []
            for field_text in (item.get("name"), item.get("description"), item.get("text")):
                text = str(field_text or "")
                if not text:
                    continue
                reasons += list(ar.placeholder_item_reasons(text))
                reasons += [r for r in ar.stat_field_rejection_reasons(text)
                            if r in ("page_scaffolding", "insubstantive")]
                reasons += list(ar.fragment_item_reasons(
                    text, section=SECTION_OF_FIELD[section]))
            if reasons:
                n += 1
                print(f"--- {rel} [{section}] reasons={sorted(set(reasons))}")
                print(f"    name={str(item.get('name'))!r} (len={len(str(item.get('name') or ''))})")
                print(f"    desc={str(item.get('description') or '')!r}")
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
            reasons = list(ar.placeholder_item_reasons(a_text))
            reasons += list(ar.stat_field_rejection_reasons(a_text))
            reasons += list(ar.template_stat_reasons(a_text))
            reasons += list(ar.fragment_scalar_reasons(a_text))
            if reasons:
                n += 1
                print(f"--- {rel} [stat:{field}] reasons={sorted(set(reasons))}")
                print(f"    text={a_text!r}")
print(f"FLAGGED_ITEMS={n}")
