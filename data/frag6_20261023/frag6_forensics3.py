#!/usr/bin/env python3
"""Frag-6 gate forensics #3: how common are code-stripped tier texts
(no '{{' codes) across the whole profiles tree, and do they carry
auto_repair provenance?"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

total = 0
stripped = []
coded = 0
for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    tier = ((prof.get("power_scale") or {}).get("tier") or {})
    if not isinstance(tier, dict):
        continue
    text = str(tier.get("text") or "")
    if not text:
        continue
    total += 1
    if "{{" in text:
        coded += 1
    else:
        stripped.append((str(path), text[:90], str(tier.get("notes") or "")))

print(f"tier_texts={total} coded={coded} code_stripped={len(stripped)}")
auto = [s for s in stripped if "auto_repair" in s[2]]
print(f"code_stripped_with_auto_repair_notes={len(auto)}")
for row in stripped[:15]:
    print("STRIPPED:", row[0].split("/")[-1], "|", row[1], "| notes:", row[2][:40])
