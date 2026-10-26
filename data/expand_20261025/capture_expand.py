"""Expand capture: snapshot the CURRENT (after) YAML of every profile in a
given list file (the gate-50), for the post-run audit.
Usage: capture_expand.py <list_json> <out_json>
The list json is {"sample": [...]} or {"first50": [...]} or a plain list.
Read-only w.r.t. profiles.
"""
import json
import sys
from pathlib import Path

import yaml

list_path, out_path = sys.argv[1], sys.argv[2]
data = json.loads(Path(list_path).read_text())
if isinstance(data, dict):
    rels = data.get("sample") or data.get("first50") or data.get("todo") or []
else:
    rels = data
actual = {}
for rel in rels:
    try:
        with open(Path("/app") / rel) as handle:
            actual[rel] = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"WARN skip {rel}: {exc}", file=sys.stderr)
Path(out_path).write_text(
    json.dumps(actual, indent=1, ensure_ascii=False, default=str))
print(json.dumps({"captured": len(actual), "of": len(rels)}))
