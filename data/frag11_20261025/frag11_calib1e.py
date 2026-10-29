#!/usr/bin/env python3
"""Frag-11 calib1e (read-only): dump the FULL single-token item-name
vocabulary (freq>=1) for the F5 bare-proper-name rule. Calib1 found
distinct=1,099; calib3 showed the freq>=2 (616) floor drops legit
hapax abilities (Immaterial, Extrasensory, Defog, Whirlwind, ...),
so the rule keys on NEVER-SEEN tokens instead. Also reports, for
each bare_proper_name hit under the OLD (freq>=2) vocab, whether the
item carries a description -- to confirm the hapax FP class.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

counts = Counter()
hit_desc = Counter()
for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    for sec in ("abilities", "weaknesses", "equipment", "resistances", "summons"):
        items = prof.get(sec)
        if isinstance(items, dict):
            items = list(items.values())
        for it in items or []:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "").strip()
            desc = str(it.get("description") or "").strip()
            toks = name.split()
            if len(toks) == 1 and toks[0].isalpha():
                counts[toks[0]] += 1
            if "bare_proper_name" in ar.fragment_item_reasons(name, section=sec):
                hit_desc["with_desc" if desc else "bare"] += 1

vocab = sorted(counts, key=str.casefold)
json.dump(vocab, open("/app/data/frag11_20261025/f5_vocab_all.json", "w"))
print(f"single_token_distinct={len(counts)} total={sum(counts.values())}")
print(f"old-rule hits: {dict(hit_desc)}")
print(f"Radagon in vocab: {'Radagon' in counts}")
print(f"Hax in vocab: {'Hax' in counts}")
print("CALIB1E DONE")
