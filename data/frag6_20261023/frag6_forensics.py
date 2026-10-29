#!/usr/bin/env python3
"""Frag-6 gate forensics: (1) rex-splode tier verbatim; (2) corpus
tier-format sample; (3) the-immortal recovered weakness items in
full + their recorded source titles/urls."""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

actual = json.loads(Path("/app/data/recovery_sample50j_actual.json").read_text())

rex = actual["profiles/needs_review/comic/image-comics/rex-splode.yaml"]
print("REX TIER FULL:", json.dumps((rex.get("power_scale") or {}).get("tier"),
                                  ensure_ascii=False))

for key in ("profiles/needs_review/comic/image-comics/the-immortal.yaml",
            "profiles/needs_review/comic/image-comics/the-immortal-image-comics.yaml"):
    prof = actual[key]
    print(f"== {key}")
    for item in prof.get("weaknesses") or []:
        print("  W:", json.dumps(item, ensure_ascii=False)[:400])
    for src in prof.get("sources") or []:
        print("  SRC:", json.dumps(src, ensure_ascii=False)[:220])

random.seed(50)
pool = [p for p in Path("/app/profiles").rglob("*.yaml")
        if "generated" in str(p)]
random.shuffle(pool)
shown = 0
for path in pool:
    if shown >= 12:
        break
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    tier = ((prof.get("power_scale") or {}).get("tier") or {})
    text = str(tier.get("text") or "") if isinstance(tier, dict) else ""
    if text:
        print("CORPUS TIER:", path.name, "|", text[:110])
        shown += 1
