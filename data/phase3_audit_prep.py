#!/usr/bin/env python3
"""Phase 3 audit prep: build actual snapshots + audit progress for the
sample-50d set, plus a human-review merge manifest of every NEW item."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

expected = json.loads(Path("/app/data/recovery_sample50d_expected.json").read_text())
sample = json.loads(Path("/app/data/recovery_sample50d_list.json").read_text())["sample"]
progress = json.loads(Path("/app/data/recovery_progress.json").read_text())

actual = {}
for rel in sample:
    path = Path(rel)
    if not path.exists():
        gen = Path(str(path).replace("profiles/needs_review/", "profiles/generated/"))
        path = gen
    with open(path) as handle:
        actual[rel] = yaml.load(handle, Loader=yaml.CSafeLoader) or {}

Path("/app/data/recovery_sample50d_actual.json").write_text(
    json.dumps(actual, indent=1, ensure_ascii=False, default=str))

recovered = {}
for rel in sample:
    entry = progress.get(rel) or {}
    if entry.get("recovered_fields"):
        recovered[rel] = entry
Path("/app/data/recovery_sample50d_audit_progress.json").write_text(
    json.dumps({"recovered": recovered}, indent=1, ensure_ascii=False, default=str))

print(f"audited_set={len(recovered)}")
for rel in sorted(recovered):
    before, after = expected[rel], actual[rel]
    sources_by_id = {str(s.get("id")): s for s in after.get("sources") or []
                     if isinstance(s, dict)}
    print(f"== {rel}")
    for section in ("power_scale", "abilities", "weaknesses", "equipment"):
        b_items = before.get(section)
        a_items = after.get(section)
        if isinstance(b_items, dict):
            b_items = list(b_items.values())
        if isinstance(a_items, dict):
            a_items = list(a_items.values())
        b_keys = {ar.normalized_identity_text(i.get("label") or i.get("key") or "")
                  for i in b_items or [] if isinstance(i, dict)}
        for item in a_items or []:
            if not isinstance(item, dict):
                continue
            key = ar.normalized_identity_text(item.get("label") or item.get("key") or "")
            if key in b_keys:
                continue
            titles = [str((sources_by_id.get(str(sid)) or {}).get("title"))
                      for sid in item.get("source_ids") or []]
            text = str(item.get("text") or "")[:110].replace("\n", " ")
            print(f"   + [{section}] {item.get('label') or item.get('key')}: {text} <- {titles}")
