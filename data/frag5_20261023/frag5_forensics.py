#!/usr/bin/env python3
"""Frag-5 gate forensics: (1) paren forensics on the audit's
unbalanced_parenthesis flags -- prove each is the item builder's
120-char name cap (name_len == 120, description paren-balanced);
(2) full current weakness lists of the three profiles whose
weakness merges are under manual-review suspicion."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

expected = json.loads(Path("/app/data/recovery_sample50i_expected.json").read_text())
actual = json.loads(Path("/app/data/recovery_sample50i_actual.json").read_text())
sample = json.loads(Path("/app/data/recovery_sample50i_list.json").read_text())["sample"]


def items(prof, section):
    value = prof.get(section)
    if isinstance(value, dict):
        return list(value.values())
    return value or []


print("== paren forensics ==")
for rel in sample:
    before, after = expected[rel], actual[rel]
    b_ids = {str(i.get("id")) for i in items(before, "abilities")
             if isinstance(i, dict)}
    for item in items(after, "abilities"):
        if not isinstance(item, dict) or str(item.get("id")) in b_ids:
            continue
        name = str(item.get("name") or "")
        desc = str(item.get("description") or "")
        if name.count("(") != name.count(")"):
            print(f"{rel.split('/')[-1]} name_len={len(name)} "
                  f"name_parens={name.count('(')}v{name.count(')')} "
                  f"desc_parens={desc.count('(')}v{desc.count(')')} "
                  f"desc_complete={desc.endswith(('.', ')'))}")

print("== full weakness lists (after) ==")
for name in ("superman-prime-earth", "starfire-dc-comics", "starfire-rebirth"):
    rel = next(r for r in sample if name in r)
    print(f"-- {name}: before={len(items(expected[rel], 'weaknesses'))} "
          f"after={len(items(actual[rel], 'weaknesses'))}")
    for item in items(actual[rel], "weaknesses"):
        if isinstance(item, dict):
            print("   W:", str(item.get("name"))[:220])
