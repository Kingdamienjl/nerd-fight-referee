#!/usr/bin/env python3
"""Final summary helpers: missing snapshot files, new H1 files, breakdowns."""
import json
import os

base = "data/h1_cleanup_20261028"
before = json.load(open(f"{base}/analysis.json"))["files"]
after = json.load(open(f"{base}/analysis_after.json"))["files"]
r1 = json.load(open(f"{base}/results.json"))
r2 = json.load(open(f"{base}/results_pass2.json"))
cleaned = dict(r1["files"])
cleaned.update(r2["files"])

missing = [p for p in before if not os.path.exists(p)]
print("missing snapshot files:", len(missing))
for p in missing:
    print("  MISSING:", p)

print("new files with H1 (not in snapshot):")
for p, v in sorted(after.items()):
    if p not in before:
        print(f"  NEW: {p} occ={v['occurrences']}")

# population breakdown of snapshot files
import collections
pop = collections.Counter()
for p in before:
    parts = p.split("/")
    pop[parts[1] if len(parts) > 1 else parts[0]] += 1
print("snapshot population:", dict(pop))

# how many snapshot files are tracked vs untracked in git
import subprocess
tracked = untracked = 0
for p in before:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", p],
                       capture_output=True)
    if r.returncode == 0:
        tracked += 1
    else:
        untracked += 1
print(f"snapshot files: tracked={tracked} untracked={untracked}")
