#!/usr/bin/env python3
"""Frag-11 calibration round 1d (read-only): F4 structural rule check.
Rule: item len<120, ends with ')', trailing paren matches
'(With ... and <LastWord>)', LastWord (len>=4) is a strict prefix of
the item's head word (len>=LastWord+2).
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

WITH_RE = re.compile(r"\(\s*With\b[^)]*\band\s+.*\b([A-Za-z]+)\)\s*$")

def item_names(prof, sections=("abilities", "weaknesses", "equipment", "resistances", "summons")):
    out = []
    for sec in sections:
        items = prof.get(sec)
        if isinstance(items, dict):
            items = list(items.values())
        for it in items or []:
            if isinstance(it, dict):
                out.append((sec, str(it.get("name") or ""), str(it.get("description") or "")))
    return out

hits = []
n = 0
for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    for sec, name, desc in item_names(prof):
        n += 1
        if len(name) >= 120:
            continue
        m = WITH_RE.search(name)
        if not m:
            continue
        last = m.group(1)
        toks = re.findall(r"[A-Za-z]+", name)
        if not toks or len(last) < 4:
            continue
        head = toks[0]
        if head.casefold().startswith(last.casefold()) and len(head) >= len(last) + 2:
            hits.append((str(path.relative_to("/app")), sec, name, last, head))
print(f"items={n} F4-structural hits={len(hits)}")
for h in hits:
    print("  F4s:", h[0], h[1], repr(h[2]), "last=", h[3], "head=", h[4])
print("verbatim:", bool(WITH_RE.search("Absorption (With Healing Drop and Deadly Absorp)")))
print("control Homing:", bool(WITH_RE.search("Homing Attack (With Homing Eye and Homing)")) and "Homing".startswith("Homing") and len("Homing") >= len("Homing")+2)
print("CALIB1D DONE")
