#!/usr/bin/env python3
"""Frag-11 cohort prep: snapshot expected state for the ENTIRE remaining
todo (all cohort entries not in progress), for the post-run audit.
Writes /app/data/recovery_cohort11_expected.json + recovery_cohort11_list.json.
Read-only w.r.t. profiles (writes only the snapshot files)."""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

spec = importlib.util.spec_from_file_location("recovery_run", "/app/data/recovery_run.py")
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)

# Mirror the runner: load the stored cohort file when present (the
# runner does NOT rebuild unless --rebuild-cohort), so the audit list
# matches the run's todo exactly.
cohort_path = Path("/app/data/recovery_cohort.json")
if cohort_path.exists():
    cohort = json.loads(cohort_path.read_text())
else:
    cohort = rr.build_cohort()
progress = rr.load_progress()
todo = [p for p in sorted(cohort) if p not in progress]

expected = {}
for rel in todo:
    try:
        with open(rel) as handle:
            expected[rel] = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
    except Exception as exc:
        print(f"WARN skip {rel}: {exc}", file=sys.stderr)

Path("/app/data/recovery_cohort11_expected.json").write_text(
    json.dumps(expected, indent=1, ensure_ascii=False, default=str))
Path("/app/data/recovery_cohort11_list.json").write_text(
    json.dumps({"cohort_total": len(cohort), "already_done": len(progress),
                "todo_total": len(todo), "todo": todo}, indent=1))
print(json.dumps({"cohort_total": len(cohort), "already_done": len(progress),
                  "todo_total": len(todo), "snapshotted": len(expected)}, indent=1))
