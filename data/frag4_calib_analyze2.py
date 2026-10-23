#!/usr/bin/env python3
"""Frag-4 calibration round 2: refined tab-key composite rules."""
import re
import sys
from collections import Counter
from pathlib import Path

names = [l.strip().strip("'\"") for l in Path(sys.argv[1]).read_text().splitlines() if l.strip()]
distinct = sorted(set(names))
print(f"names={len(names)} distinct={len(distinct)}")
TARGET = "Base Hax Hammer Harleen Hax AoR Harley Hax Death Manipulation"


def toks(name):
    return re.findall(r"[A-Za-z0-9']+", name)


def show(label, hits, limit=30):
    print(f"\n--- {label}: {len(hits)} hits")
    for h in hits[:limit]:
        print("   ", repr(h))


# C1: exact-case token 'Hax' >= 2
c1 = [n for n in distinct if Counter(toks(n))["Hax"] >= 2]
show("C1 exact-case 'Hax' >=2", c1)

# C1b: exact-case 'Hax' >= 1 and >=6 tokens and a repeat of any token
c1b = [n for n in distinct if Counter(toks(n))["Hax"] >= 1 and len(toks(n)) >= 6
       and any(c >= 2 for c in Counter(t.casefold() for t in toks(n)).values())]
show("C1b 'Hax'>=1 + >=6 toks + repeat", c1b)

# C2: short (<=4) Title-case token repeated >=3 in >=6-token name
def c2(n):
    ts = toks(n)
    if len(ts) < 6:
        return False
    return any(c >= 3 and len(t) <= 4 and t[:1].isupper()
               for t, c in Counter(ts).items())

c2h = [n for n in distinct if c2(n)]
show("C2 short Title token x3 in >=6tok", c2h)

# C3: name has >=6 tokens, every alpha token Title-case (first upper, rest lower
# or single letter), no '*' and no ':' and a repeated casefold token
def titleish(t):
    return t[:1].isupper() and (len(t) == 1 or t[1:].islower() or t.isupper())

def c3(n):
    if "*" in n or ":" in n:
        return False
    ts = toks(n)
    if len(ts) < 6:
        return False
    if not all(titleish(t) for t in ts if t.isalpha()):
        return False
    return any(c >= 2 for c in Counter(t.casefold() for t in ts).values())

c3h = [n for n in distinct if c3(n)]
show("C3 >=6 toks all-Title + repeat (no * or :)", c3h)

# C4: C1 or C3
c4 = [n for n in distinct if n in set(c1) or c3(n)]
show("C4 = C1 or C3", c4)
print("\nTARGET:", TARGET in distinct, "| C1:", TARGET in set(c1), "| C3:", c3(TARGET), "| C2:", c2(TARGET))
