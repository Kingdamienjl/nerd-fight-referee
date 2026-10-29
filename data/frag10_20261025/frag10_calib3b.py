#!/usr/bin/env python3
"""Frag-10 calib3b (read-only): full texts of every stat value the
refined media_filename rule flags, for hand review."""
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar


def stat_texts(prof):
    ps = prof.get("power_scale") or {}
    out = {}
    if isinstance(ps, dict):
        for field, val in ps.items():
            if isinstance(val, dict):
                out[field] = str(val.get("text") or "")
            elif isinstance(val, str):
                out[field] = val
    return out


n = 0
for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    for field, text in stat_texts(prof).items():
        if not text:
            continue
        if "media_fragment" in ar.boilerplate_reasons(text, scalar=True):
            n += 1
            print(f"--- {n} [{field}] {path.name}")
            print(text)
print(f"TOTAL media hits: {n}")
print("CALIB3B DONE")
