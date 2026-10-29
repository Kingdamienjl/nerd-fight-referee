#!/usr/bin/env python3
"""Frag-11: print the error field of every progress entry that has one."""
import json
from pathlib import Path

p = json.loads(Path("/app/data/recovery_progress.json").read_text())
errs = {k: v for k, v in p.items() if (v or {}).get("error")}
print("error_entries:", len(errs))
for rel, ent in sorted(errs.items()):
    print(rel.split("/")[-1], "|", str(ent.get("error"))[:200])
