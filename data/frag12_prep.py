#!/usr/bin/env python3
"""Frag-12 re-gate prep (50p): rebuild cohort, compute the sample set,
snapshot expected profile state. Adapted from frag11_prep.py (50o).

Quarantine rule for the gate: the 9 frag-11-quarantined profiles stay
out of the gate sample. The other 7 are excluded automatically (their
progress entries are flagged quarantined_frag11, so they are not in
todo). asmoday/ronova had their progress entries REMOVED by the
frag-11 quarantine script, so they would re-enter todo -- exclude
them explicitly here and take the next todo entries instead. They
re-enter only for the mass run, after the gate passes.
"""
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

QUARANTINED_BASENAMES = {"asmoday.yaml", "ronova.yaml"}

cohort = rr.build_cohort()
progress = rr.load_progress()
todo = [p for p in sorted(cohort) if p not in progress]
excluded = [p for p in todo[:60] if Path(p).name in QUARANTINED_BASENAMES]
sample = [p for p in todo if Path(p).name not in QUARANTINED_BASENAMES][:50]

expected = {}
for rel in sample:
    with open("/app/" + rel) as handle:
        expected[rel] = yaml.load(handle, Loader=yaml.CSafeLoader) or {}

Path("/app/data/recovery_sample50p_expected.json").write_text(
    json.dumps(expected, indent=1, ensure_ascii=False, default=str))
Path("/app/data/recovery_sample50p_list.json").write_text(
    json.dumps({"cohort_total": len(cohort), "already_done": len(progress),
                "todo_total": len(todo), "quarantined_excluded_from_gate": excluded,
                "sample": sample}, indent=1))
print(json.dumps({"cohort_total": len(cohort), "already_done": len(progress),
                  "todo_total": len(todo),
                  "quarantined_excluded_from_gate": excluded,
                  "sample_size": len(sample),
                  "sample_first": sample[0] if sample else None,
                  "sample_last": sample[-1] if sample else None}, indent=1))
