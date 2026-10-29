#!/usr/bin/env python3
"""Frag-5 calibration: run the EXTENDED fragment_item_reasons over
every weakness item text in generated + needs_review profiles and
report every prose_shard_continuation hit for manual review."""
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

hits = []
total = 0
profiles = 0
for base in ("/app/profiles/generated", "/app/profiles/needs_review"):
    for path in sorted(Path(base).rglob("*.yaml")):
        try:
            with path.open() as handle:
                prof = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
        except Exception:
            continue
        profiles += 1
        items = prof.get("weaknesses")
        if isinstance(items, dict):
            items = list(items.values())
        for item in items or []:
            texts = []
            if isinstance(item, dict):
                for key in ("name", "text", "description"):
                    if item.get(key):
                        texts.append(str(item[key]))
            elif isinstance(item, str):
                texts.append(item)
            for text in texts:
                total += 1
                reasons = ar.fragment_item_reasons(text, section="weaknesses")
                if "prose_shard_continuation" in reasons:
                    hits.append({"profile": str(path), "text": text[:200],
                                 "reasons": reasons})

out = {"profiles": profiles, "total_texts": total,
       "hits": len(hits), "hit_list": hits}
Path("/app/data/frag5_20261023/calib.json").write_text(
    json.dumps(out, indent=1, ensure_ascii=False))
print(f"profiles={profiles} total_texts={total} hits={len(hits)}")
for hit in hits:
    print("HIT:", hit["text"], "|", hit["profile"].split("/")[-1])
