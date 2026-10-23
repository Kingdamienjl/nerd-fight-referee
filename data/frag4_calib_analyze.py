#!/usr/bin/env python3
"""Frag-4 calibration analysis: test tab-key composite rule candidates
against the dumped corpus of item names."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

names = [l.strip().strip("'\"") for l in Path(sys.argv[1]).read_text().splitlines() if l.strip()]
print(f"names={len(names)} distinct={len(set(names))}")

TARGET = "Base Hax Hammer Harleen Hax AoR Harley Hax Death Manipulation"


def toks(name):
    return re.findall(r"[A-Za-z0-9']+", name)


def show(label, hits, limit=25):
    print(f"\n--- {label}: {len(hits)} hits")
    for h in hits[:limit]:
        print("   ", repr(h))


# R1: any token repeated >=3 times
r1 = [n for n in set(names) if any(c >= 3 for c in Counter(t.casefold() for t in toks(n)).values())]
show("R1 token repeated >=3x", sorted(r1))

# R2: 'hax' token >=2 times
r2 = [n for n in set(names) if Counter(t.casefold() for t in toks(n))["hax"] >= 2]
show("R2 'hax' token >=2x", sorted(r2))

# R2b: any 'hax' token at all
r2b = [n for n in set(names) if "hax" in [t.casefold() for t in toks(n)]]
show("R2b any 'hax' token", sorted(r2b))

# R3: >=7 tokens, some token repeated, no lowercase-start token after first
def all_capitalizedish(n):
    ts = toks(n)
    return len(ts) >= 7 and all(t[:1].isupper() or not t.isalpha() for t in ts)

r3 = [n for n in set(names) if all_capitalizedish(n) and any(c >= 2 for c in Counter(t.casefold() for t in toks(n)).values())]
show("R3 >=7 toks all-cap + repeat", sorted(r3))

# R4: union candidate
def candidate(n):
    ts = [t.casefold() for t in toks(n)]
    counts = Counter(ts)
    if counts["hax"] >= 2:
        return True
    if any(c >= 3 for c in counts.values()):
        return True
    return False

r4 = [n for n in set(names) if candidate(n)]
show("R4 = R1 or R2", sorted(r4))
print("\nTARGET in corpus:", TARGET in set(names))
print("TARGET candidate():", candidate(TARGET))
