#!/usr/bin/env python3
"""Verify H1 cleanup:
1. Every snapshotted file still parses as YAML.
2. For each cleaned file, diff backup-archive copy vs current: only
   deletions allowed, and deleted-line count must equal the debris span
   total for that file.
Usage: verify.py <analysis.json> <results.json> <results_pass2.json> <backup_tar>"""
import json
import subprocess
import sys

import yaml

analysis = json.load(open(sys.argv[1]))
r1 = json.load(open(sys.argv[2]))
r2 = json.load(open(sys.argv[3]))
backup_tar = sys.argv[4]

cleaned = dict(r1["files"])
cleaned.update(r2["files"])

parse_fail = []
for path in sorted(analysis["files"]):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            list(yaml.compose_all(f.read()))
    except yaml.YAMLError as e:
        parse_fail.append((path, str(e)[:150]))

print(f"parse check: {len(analysis['files'])} files, failures={len(parse_fail)}")
for p, e in parse_fail:
    print(" PARSE-FAIL:", p, e)

bad = []
tot_del = tot_add = 0
for path, v in sorted(cleaned.items()):
    if v["debris_items"] == 0:
        continue
    # expected deleted lines = sum of debris span lengths
    spans = []
    for it in analysis["files"][path]["items"]:
        # debris items are those NOT in skipped list (match by start line)
        skip_starts = {s["start_line_1b"] for s in v["skipped_items"]}
        if it["start_line_1b"] not in skip_starts:
            spans.append((it["start_line_1b"], it["end_line_1b"]))
    expected = sum(e - s + 1 for s, e in spans)
    tar = subprocess.run(
        ["tar", "-xzOf", backup_tar, path],
        capture_output=True, text=True,
    )
    if tar.returncode != 0:
        bad.append((path, "not in backup tar"))
        continue
    diff = subprocess.run(
        ["diff", "-", path],
        input=tar.stdout, capture_output=True, text=True,
    )
    deleted = added = 0
    for line in diff.stdout.splitlines():
        if line.startswith("<"):
            deleted += 1
        elif line.startswith(">"):
            added += 1
    tot_del += deleted
    tot_add += added
    if added != 0 or deleted != expected:
        bad.append((path, f"added={added} deleted={deleted} expected={expected}"))
print(f"diff check: files={sum(1 for v in cleaned.values() if v['debris_items']>0)} "
      f"total_deleted={tot_del} total_added={tot_add} mismatches={len(bad)}")
for p, e in bad:
    print(" DIFF-MISMATCH:", p, e)
