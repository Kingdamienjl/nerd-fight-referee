#!/usr/bin/env python3
"""Frag-6 calib drill-down: sample technique hits by shape."""
import json
import random
import re
from pathlib import Path

data = json.loads(Path("/app/data/frag6_20261023/calib.json").read_text())
hits = data["hits"]["technique_in_weaknesses"]

seen = {}
for hit in hits:
    norm = re.sub(r"\s+", " ", hit["text"].strip().casefold())[:160]
    seen.setdefault(norm, hit)
distinct = list(seen.values())
print(f"distinct={len(distinct)}")

short = [h for h in distinct if len(h["text"]) < 70]
print(f"--- SHORT (<70 chars): {len(short)} ---")
for h in short[:45]:
    print("S:", h["text"][:150], "|", h["profile"].split("/")[-1])

random.seed(6)
rest = [h for h in distinct if len(h["text"]) >= 70]
print(f"--- RANDOM LONG: {len(rest)} ---")
for h in random.sample(rest, 35):
    print("L:", h["text"][:170], "|", h["profile"].split("/")[-1])

sus = [h for h in distinct if re.search(r"\bweaken|\bhim\b|\bher\b", h["text"].casefold())]
print(f"--- HIM/HER/WEAKEN subset: {len(sus)} ---")
for h in sus[:25]:
    print("W:", h["text"][:170], "|", h["profile"].split("/")[-1])
