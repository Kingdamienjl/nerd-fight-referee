#!/usr/bin/env python3
"""Cohort spot-check: (a) every Nth unflagged merge (deterministic sample),
(b) unflagged items whose description looks like a whole-section glue
(>=4 parenthetical ability heads), (c) counts. Prints full text."""
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
SECTION_OF_FIELD = {"abilities": "powers_and_abilities", "weaknesses": "weaknesses", "equipment": "standard_equipment"}
HEAD_RE = re.compile(r"\b[A-Z][A-Za-z]+ (Manipulation|Creation|Control|Negation|Resistance|Immunity|Physiology|Projection|Generation|Absorption|Amplification|Perception)\s*\(")

def item_key(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or "") or ar.normalized_identity_text(
        item.get("name") or item.get("label") or "")

def flagged(item, section, text=None):
    reasons = []
    for t in (item.get("name"), item.get("description"), item.get("text")):
        t = str(t or "")
        if not t:
            continue
        reasons += list(ar.placeholder_item_reasons(t))
        reasons += [r for r in ar.stat_field_rejection_reasons(t)
                    if r in ("page_scaffolding", "insubstantive")]
        reasons += list(ar.fragment_item_reasons(t, section=SECTION_OF_FIELD[section]))
    return bool(reasons)

unflagged = []
glue = []
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
            if flagged(item, section):
                continue
            unflagged.append((rel, section, item))
            desc = str(item.get("description") or "")
            if len(HEAD_RE.findall(desc)) >= 4:
                glue.append((rel, section, item, len(HEAD_RE.findall(desc))))

print(f"unflagged_items={len(unflagged)} glue_candidates={len(glue)}")
print("== (a) every 25th unflagged item ==")
for i, (rel, section, item) in enumerate(unflagged):
    if i % 25 == 0:
        print(f"--- [{i}] {rel} [{section}] name={str(item.get('name'))!r}")
        print(f"    desc={str(item.get('description') or '')[:300]!r}")
print("== (b) whole-section glue candidates (desc with >=4 ability heads) ==")
for rel, section, item, nheads in glue:
    print(f"--- {rel} [{section}] heads={nheads} name={str(item.get('name'))[:100]!r}")
    print(f"    desc_len={len(str(item.get('description') or ''))} desc={str(item.get('description') or '')[:200]!r}")
print("SPOTCHECK DONE")
