#!/usr/bin/env python3
"""Frag-6 gate 50j revert verification: for both immortal profiles,
weaknesses must equal the pre-run snapshot exactly and every other
top-level section must equal the post-run (audited) actual state."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

expected = json.loads(Path("/opt/referee/data/recovery_sample50j_expected.json").read_text())
actual = json.loads(Path("/opt/referee/data/recovery_sample50j_actual.json").read_text())
progress = json.loads(Path("/opt/referee/data/recovery_progress.json").read_text())

ok = True
for rel in ("profiles/needs_review/comic/image-comics/the-immortal.yaml",
            "profiles/needs_review/comic/image-comics/the-immortal-image-comics.yaml"):
    live = yaml.load(open("/opt/referee/" + rel), Loader=yaml.CSafeLoader) or {}
    live = json.loads(json.dumps(live, ensure_ascii=False, default=str))
    checks = {
        "weaknesses==expected": live.get("weaknesses") == expected[rel].get("weaknesses"),
        "abilities==actual": live.get("abilities") == actual[rel].get("abilities"),
        "power_scale==actual": live.get("power_scale") == actual[rel].get("power_scale"),
        "progress_key_absent": rel not in progress,
    }
    print(rel, checks)
    ok = ok and all(checks.values())
print("VERIFY:", "PASS" if ok else "FAIL")
