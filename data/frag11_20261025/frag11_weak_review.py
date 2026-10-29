#!/usr/bin/env python3
"""List every NEW weakness item (cohort, post-run-5) for manual review,
so the lore-fragment wrong-section shape can be scoped precisely."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

exp = json.loads(Path("/app/data/recovery_cohort11_expected.json").read_text())
act = json.loads(Path("/app/data/recovery_cohort11_actual.json").read_text())
todo = json.loads(Path("/app/data/recovery_cohort11_list.json").read_text())["todo"]
prog = json.loads(Path("/app/data/recovery_progress.json").read_text())

def key(it):
    return str(it.get("id") or "") or ar.normalized_identity_text(
        it.get("name") or it.get("label") or "")

n = 0
for rel in todo:
    if not (prog.get(rel) or {}).get("recovered_fields"):
        continue
    b = exp[rel]
    a = act[rel]
    bw = b.get("weaknesses") or []
    aw = a.get("weaknesses") or []
    if isinstance(bw, dict):
        bw = list(bw.values())
    if isinstance(aw, dict):
        aw = list(aw.values())
    bk = {key(i) for i in bw if isinstance(i, dict)}
    for w in aw:
        if isinstance(w, dict) and key(w) not in bk:
            n += 1
            print(rel.split("/")[-1], "|", repr(str(w.get("name"))[:120]), "| id:", w.get("id"))
print("total_new_weakness_items:", n)
