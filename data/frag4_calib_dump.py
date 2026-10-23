#!/usr/bin/env python3
"""Frag-4 calibration: dump every item name in the profile corpus."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io

ROOT = Path("/app/profiles")
SECTIONS = ("abilities", "equipment", "summons", "resistances", "weaknesses")
names = []
files = 0
for path in sorted(ROOT.rglob("*.yaml")):
    try:
        profile = yaml_io.load_yaml(path)
    except Exception:
        continue
    if not isinstance(profile, dict):
        continue
    files += 1
    for section in SECTIONS:
        for item in profile.get(section) or []:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name:
                    names.append(name)
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())
out = Path("/app/data/frag4_calib_names.json")
out.write_text(json.dumps({"files": files, "names": names}, ensure_ascii=False))
print(f"files={files} names={len(names)}")
