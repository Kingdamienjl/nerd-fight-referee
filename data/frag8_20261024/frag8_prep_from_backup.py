#!/usr/bin/env python3
"""Frag-8 gate prep from the pre-gate backup (the gate was launched
before prep ran, so live files are already mutating -- the backup tar
is the authoritative pre-run snapshot).

Reads cohort + progress from the gate backup's .before.json files,
computes sample = first 50 of sorted todo (same logic as
frag8_prep.py), extracts the 50 profiles from profiles.tar.gz, and
writes /app/data/recovery_sample50l_expected.json +
/app/data/recovery_sample50l_list.json (the paths frag8_actual.py and
frag8_audit.py read).
"""
import io
import json
import tarfile
from pathlib import Path

import yaml

B = Path("/opt/referee/backups/20261024-frag8-gate")
cohort = json.loads((B / "recovery_cohort.before.json").read_text())
progress = json.loads((B / "recovery_progress.before.json").read_text())
todo = [p for p in sorted(cohort) if p not in progress]
sample = todo[:50]

expected = {}
with tarfile.open(B / "profiles.tar.gz", "r:gz") as tf:
    for rel in sample:
        member = tf.getmember(rel)
        with tf.extractfile(member) as handle:
            expected[rel] = yaml.load(handle, Loader=yaml.CSafeLoader) or {}

Path("/app/data/recovery_sample50l_expected.json").write_text(
    json.dumps(expected, indent=1, ensure_ascii=False, default=str))
Path("/app/data/recovery_sample50l_list.json").write_text(
    json.dumps({"cohort_total": len(cohort), "already_done": len(progress),
                "todo_total": len(todo), "sample": sample}, indent=1))
print(json.dumps({"cohort_total": len(cohort), "already_done": len(progress),
                  "todo_total": len(todo), "sample_size": len(sample),
                  "sample_first": sample[0], "sample_last": sample[-1]},
                 indent=1))
