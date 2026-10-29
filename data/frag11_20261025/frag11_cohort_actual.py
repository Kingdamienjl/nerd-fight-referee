#!/usr/bin/env python3
"""Frag-11 cohort actuals: snapshot post-run state for the cohort todo list."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

todo = json.loads(Path("/app/data/recovery_cohort11_list.json").read_text())["todo"]
actual = {}
for rel in todo:
    try:
        with open(rel) as handle:
            actual[rel] = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
    except Exception as exc:
        print(f"WARN skip {rel}: {exc}", file=sys.stderr)
Path("/app/data/recovery_cohort11_actual.json").write_text(
    json.dumps(actual, indent=1, ensure_ascii=False, default=str))
print(f"snapshotted {len(actual)} profiles")
