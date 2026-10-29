#!/usr/bin/env python3
"""Frag-6 re-gate prep (50j): rebuild cohort, compute the sample
set, snapshot expected profile state. The run itself is launched
parser-only (HARVEST_LLM_FALLBACK=0)."""
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

cohort = rr.build_cohort()
progress = rr.load_progress()
todo = [p for p in sorted(cohort) if p not in progress]
sample = todo[:50]

expected = {}
for rel in sample:
    with open(rel) as handle:
        expected[rel] = yaml.load(handle, Loader=yaml.CSafeLoader) or {}

Path("/app/data/recovery_sample50j_expected.json").write_text(
    json.dumps(expected, indent=1, ensure_ascii=False, default=str))
Path("/app/data/recovery_sample50j_list.json").write_text(
    json.dumps({"cohort_total": len(cohort), "already_done": len(progress),
                "todo_total": len(todo), "sample": sample}, indent=1))
print(json.dumps({"cohort_total": len(cohort), "already_done": len(progress),
                  "todo_total": len(todo), "sample_size": len(sample),
                  "sample_first": sample[0] if sample else None,
                  "sample_last": sample[-1] if sample else None}, indent=1))
