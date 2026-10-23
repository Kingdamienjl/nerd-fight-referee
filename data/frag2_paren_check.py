#!/usr/bin/env python3
"""Paren-balance forensics for audit-flagged items: for every merged
item whose NAME alone is paren-unbalanced, print name/description
paren counts, combined balance, and the description tail. If the
combined text balances and the description ends complete, the flag
is the known 120-char name-truncation artifact."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

expected = json.loads(Path("/app/data/recovery_sample50f_expected.json").read_text())
actual = json.loads(Path("/app/data/recovery_sample50f_actual.json").read_text())
sample = json.loads(Path("/app/data/recovery_sample50f_list.json").read_text())["sample"]
progress = json.loads(Path("/app/data/recovery_progress.json").read_text())


def item_key(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or "") or ar.normalized_identity_text(
        item.get("name") or item.get("label") or "")


def counts(text):
    return text.count("("), text.count(")")


rows = 0
bad = 0
for rel in sample:
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
            name = str(item.get("name") or "")
            desc = str(item.get("description") or "")
            no, nc = counts(name)
            if no == nc:
                continue
            do, dc = counts(desc)
            combined_ok = (no + do) == (nc + dc)
            rows += 1
            if not combined_ok:
                bad += 1
            print(f"{rel} [{section}] name_len={len(name)} name=({no},{nc}) "
                  f"desc=({do},{dc}) combined_balanced={combined_ok}")
            print(f"  name_tail={name[-45:]!r}")
            print(f"  desc_head={desc[:60]!r} desc_tail={desc[-60:]!r}")
print(f"flagged_items={rows} combined_unbalanced={bad}")
