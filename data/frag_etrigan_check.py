#!/usr/bin/env python3
"""Was the etrigan footer weakness item present in the BEFORE snapshot
(under any key), and what exactly did recovery's merging attempt drop?"""
import json
from pathlib import Path

REL = "profiles/needs_review/comic/dc/etrigan-dc-comics.yaml"
expected = json.loads(Path("/app/data/recovery_sample50e_expected.json").read_text())
actual = json.loads(Path("/app/data/recovery_sample50e_actual.json").read_text())
progress = json.loads(Path("/app/data/recovery_progress.json").read_text())


def items(prof, section):
    items = prof.get(section)
    if isinstance(items, dict):
        items = list(items.values())
    return [i for i in items or [] if isinstance(i, dict)]


for label, prof in (("BEFORE", expected[REL]), ("AFTER", actual[REL])):
    print(f"== {label} weaknesses ({len(items(prof, 'weaknesses'))})")
    for i in items(prof, "weaknesses"):
        print(f"   id={i.get('id')!r} name={str(i.get('name'))[:70]!r}")

entry = progress[REL]
print("recovered_fields:", entry.get("recovered_fields"))
print("merges:", entry.get("merges"))
for t in entry.get("sources_tried") or []:
    print("TRIED source:", t.get("source_id"), "guard accepted:",
          (t.get("guard") or {}).get("accepted"), "scoped:", t.get("scoped_fields"))
    for field, drops in (t.get("dropped_items") or {}).items():
        for d in drops:
            print(f"   DROP[{field}] {d.get('reasons')} :: {str(d.get('item'))[:160]!r}")
    for field in t.get("boilerplate_fields") or []:
        print(f"   FIELD_DROP {field} :: {(t.get('boilerplate_reasons') or {}).get(field)}")
