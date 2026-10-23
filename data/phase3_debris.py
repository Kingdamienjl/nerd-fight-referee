#!/usr/bin/env python3
"""Print full id/name/description of suspicious NEW items in the
fragment-candidate profiles of sample 50d."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

expected = json.loads(Path("/app/data/recovery_sample50d_expected.json").read_text())
TARGETS = [
    "profiles/needs_review/comic/dc/beast-boy-dc-comics.yaml",
    "profiles/needs_review/comic/dc/beast-boy-post-crisis.yaml",
    "profiles/needs_review/comic/dc/beast-boy-post-flashpoint.yaml",
    "profiles/needs_review/comic/dc/beast-boy-rebirth.yaml",
    "profiles/needs_review/comic/dc/big-barda-dc-comics.yaml",
    "profiles/needs_review/comic/dc/circe.yaml",
    "profiles/needs_review/comic/dc/circe-dc-comics.yaml",
]

for rel in TARGETS:
    with open(rel) as handle:
        after = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
    before = expected[rel]
    print(f"===== {rel}")
    b_ps = before.get("power_scale") or {}
    a_ps = after.get("power_scale") or {}
    if isinstance(a_ps, dict):
        for field, item in a_ps.items():
            if isinstance(item, dict):
                bt = str((b_ps.get(field) or {}).get("text") or "") if isinstance(b_ps, dict) else ""
                at = str(item.get("text") or "")
                if at and at != bt and (at.startswith(",") or at.startswith(" ")):
                    print(f"  TIERLIKE [{field}] before={bt!r} after={at!r}")
    for section in ("abilities", "weaknesses"):
        b_items = before.get(section)
        a_items = after.get(section)
        if isinstance(b_items, dict):
            b_items = list(b_items.values())
        if isinstance(a_items, dict):
            a_items = list(a_items.values())
        b_ids = {str(i.get("id")) for i in b_items or [] if isinstance(i, dict)}
        for item in a_items or []:
            if not isinstance(item, dict) or str(item.get("id")) in b_ids:
                continue
            name = str(item.get("name") or "")
            desc = str(item.get("description") or "")
            suspicious = (
                name.startswith("and ") or name.endswith(" and")
                or name.startswith("Resistance to:") or ")" in name.split("(")[0]
                or "," in name and ")," in name or "Notable" in desc
                or "http" in desc or len(desc) < 12)
            if suspicious:
                print(f"  [{section}] id={item.get('id')}")
                print(f"      name={name!r}")
                print(f"      desc={desc[:200]!r}")
