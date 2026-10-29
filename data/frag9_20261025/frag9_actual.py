#!/usr/bin/env python3
"""Frag-8 post-run snapshot: current state of the sample-50m set."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

sample = json.loads(
    Path("/app/data/recovery_sample50m_list.json").read_text())["sample"]
actual = {}
for rel in sample:
    path = Path(rel)
    if not path.exists() and rel.startswith("profiles/needs_review/"):
        moved = Path(rel.replace("profiles/needs_review/", "profiles/generated/", 1))
        if moved.exists():
            path = moved
    with path.open() as handle:
        actual[rel] = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
Path("/app/data/recovery_sample50m_actual.json").write_text(
    json.dumps(actual, indent=1, ensure_ascii=False, default=str))
print(f"snapshotted {len(actual)} profiles")
