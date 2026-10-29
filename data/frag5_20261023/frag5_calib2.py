#!/usr/bin/env python3
"""Frag-5 calibration v2: prose_shard_continuation hits by field.
The recovery itemizer emits short list entries; the corpus proxy is
item NAMES (the frag-2 calibration basis). Report hits separately
for name / text / description so the false-positive surface of each
field is visible."""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

spec = importlib.util.spec_from_file_location(
    "ar_frag5", "/app/data/frag5_20261023/auto_repair_new.py")
ar = importlib.util.module_from_spec(spec)
sys.modules["ar_frag5"] = ar
spec.loader.exec_module(ar)

per_field = {}
examples = {}
for base in ("/app/profiles/generated", "/app/profiles/needs_review"):
    for path in sorted(Path(base).rglob("*.yaml")):
        try:
            with path.open() as handle:
                prof = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
        except Exception:
            continue
        items = prof.get("weaknesses")
        if isinstance(items, dict):
            items = list(items.values())
        for item in items or []:
            fields = {}
            if isinstance(item, dict):
                for key in ("name", "text", "description"):
                    if item.get(key):
                        fields[key] = str(item[key])
            elif isinstance(item, str):
                fields["name"] = item
            for key, text in fields.items():
                slot = per_field.setdefault(key, {"total": 0, "hits": 0})
                slot["total"] += 1
                reasons = ar.fragment_item_reasons(text, section="weaknesses")
                if "prose_shard_continuation" in reasons:
                    slot["hits"] += 1
                    bucket = examples.setdefault(key, [])
                    if len(bucket) < 60:
                        bucket.append({"profile": path.name, "text": text[:180]})

Path("/app/data/frag5_20261023/calib2.json").write_text(
    json.dumps({"per_field": per_field, "examples": examples},
               indent=1, ensure_ascii=False))
print(json.dumps(per_field, indent=1))
for key, bucket in examples.items():
    print(f"== {key} examples ==")
    for ex in bucket:
        print("HIT:", ex["text"], "|", ex["profile"])
