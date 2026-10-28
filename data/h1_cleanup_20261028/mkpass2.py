#!/usr/bin/env python3
"""Build a pass-2 analysis containing only the files the first pass flagged
as changed-skipped, so clean.py can re-process just those."""
import json
import sys

analysis = json.load(open(sys.argv[1]))
results = json.load(open(sys.argv[2]))
changed = [c["file"] for c in results["changed_skipped"]]
out = {"files": {}, "failures": [], "rt_only": []}
for path in changed:
    if path in analysis["files"]:
        out["files"][path] = analysis["files"][path]
    else:
        print("WARNING: changed file not in analysis:", path)
with open(sys.argv[3], "w") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
print(f"pass2 files: {len(out['files'])}")
