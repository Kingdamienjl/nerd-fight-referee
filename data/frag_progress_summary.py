#!/usr/bin/env python3
"""Summarize the sample-50e run from the authoritative progress file."""
import json
from pathlib import Path

prog = json.loads(Path("/app/data/recovery_progress.json").read_text())
lst = json.loads(Path("/app/data/recovery_sample50e_list.json").read_text())
sample = lst["sample"]
got = [p for p in sample if p in prog]
rec = {p: prog[p].get("recovered_fields") for p in got if prog[p].get("recovered_fields")}
prom = [p for p in got if prog[p].get("promoted")]
errs = {p: prog[p].get("error") for p in got if prog[p].get("error")}
ident = [p for p in got if prog[p].get("identity_mismatch")]
print(f"todo_total={lst['todo_total']} cohort_total={lst['cohort_total']} already_done={lst['already_done']}")
print(f"in_progress={len(got)} recovered={len(rec)} promoted={len(prom)} "
      f"errors={len(errs)} identity_mismatch={len(ident)}")
for p, f in sorted(rec.items()):
    print("REC", p, f)
for p in prom:
    print("PROMOTED", p)
for p, e in errs.items():
    print("ERR", p, e)
# dropped-item / dropped-field evidence recorded by the screens
drops = 0
for p in got:
    for t in prog[p].get("sources_tried") or []:
        di = t.get("dropped_items") or {}
        for field, items in di.items():
            for it in items:
                drops += 1
                print("DROP", p, field, it.get("reasons"), str(it.get("item"))[:80])
        bf = t.get("boilerplate_fields") or []
        br = t.get("boilerplate_reasons") or {}
        for field in bf:
            print("FIELD_DROP", p, field, br.get(field))
print(f"dropped_items_total={drops}")
