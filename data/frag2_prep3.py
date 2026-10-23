#!/usr/bin/env python3
"""Part-3 re-gate prep (50f): rebuild cohort, compute the sample set,
snapshot expected profile state, one LiteLLM liveliness check."""
import importlib.util
import json
import sys
import urllib.request
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

Path("/app/data/recovery_sample50f_expected.json").write_text(
    json.dumps(expected, indent=1, ensure_ascii=False, default=str))
Path("/app/data/recovery_sample50f_list.json").write_text(
    json.dumps({"cohort_total": len(cohort), "already_done": len(progress),
                "todo_total": len(todo), "sample": sample}, indent=1))

llm_status = "unknown"
try:
    req = urllib.request.Request("http://litellm:4000/health/liveliness",
                                 headers={"User-Agent": "frag2-prep/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        llm_status = f"http {resp.status}"
except Exception as exc:  # noqa: BLE001
    llm_status = f"unreachable: {type(exc).__name__}: {exc}"

print(json.dumps({"cohort_total": len(cohort), "already_done": len(progress),
                  "todo_total": len(todo), "sample_size": len(sample),
                  "sample_first": sample[0] if sample else None,
                  "sample_last": sample[-1] if sample else None,
                  "litellm": llm_status}, indent=1))
