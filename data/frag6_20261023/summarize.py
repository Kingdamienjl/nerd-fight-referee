#!/usr/bin/env python3
"""Summarize frag6 calib.json: distinct hit texts per screen kind."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

data = json.loads(Path("/app/data/frag6_20261023/calib.json").read_text())
kind = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50

counter = Counter()
example = {}
for hit in data["hits"][kind]:
    norm = re.sub(r"\s+", " ", hit["text"].strip().casefold())[:160]
    counter[norm] += 1
    example.setdefault(norm, hit)
print(f"{kind}: raw={sum(counter.values())} distinct={len(counter)}")
shown = 0
for norm, count in counter.most_common():
    if shown >= limit:
        break
    hit = example[norm]
    print(f"[{count}x] {hit['text'][:190]} | {hit['profile'].split('/')[-1]}")
    shown += 1
