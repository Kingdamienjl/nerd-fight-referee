#!/usr/bin/env python3
"""Fragment-gate audit prep: actual snapshots + recovered-set file for 50e."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

expected = json.loads(Path("/app/data/recovery_sample50e_expected.json").read_text())
sample = json.loads(Path("/app/data/recovery_sample50e_list.json").read_text())["sample"]
progress = json.loads(Path("/app/data/recovery_progress.json").read_text())

actual = {}
for rel in sample:
    path = Path(rel)
    if not path.exists():
        path = Path(str(path).replace("profiles/needs_review/", "profiles/generated/"))
    with open(path) as handle:
        actual[rel] = yaml.load(handle, Loader=yaml.CSafeLoader) or {}

Path("/app/data/recovery_sample50e_actual.json").write_text(
    json.dumps(actual, indent=1, ensure_ascii=False, default=str))

recovered = {}
for rel in sample:
    entry = progress.get(rel) or {}
    if entry.get("recovered_fields"):
        recovered[rel] = entry
Path("/app/data/recovery_sample50e_audit_progress.json").write_text(
    json.dumps({"recovered": recovered}, indent=1, ensure_ascii=False, default=str))

print(f"audited_set={len(recovered)}")
print("recovered_profiles:", *sorted(recovered), sep="\n  ")
