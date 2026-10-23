#!/usr/bin/env python3
"""Frag-4 calibration round 3: final candidate on generated-only names."""
import re
import sys
from collections import Counter
from pathlib import Path

names = [l.strip().strip("'\"") for l in Path(sys.argv[1]).read_text().splitlines() if l.strip()]
distinct = sorted(set(names))
print(f"generated names={len(names)} distinct={len(distinct)}")
TARGET = "Base Hax Hammer Harleen Hax AoR Harley Hax Death Manipulation"


def toks(name):
    return re.findall(r"[A-Za-z0-9']+", name)


def show(label, hits, limit=40):
    print(f"\n--- {label}: {len(hits)} hits")
    for h in hits[:limit]:
        print("   ", repr(h))


def tabkey(n):
    """Final candidate: a repeated tab/category label.
    (i) exact-case 'Hax' token >= 2, or
    (ii) a short (<=5) Title-case token repeated >= 3 in a >=6-token item."""
    ts = toks(n)
    counts = Counter(ts)
    if counts["Hax"] >= 2:
        return True
    if len(ts) >= 6 and any(
        c >= 3 and len(t) <= 5 and t[:1].isupper() and t.isalpha()
        for t, c in counts.items()
    ):
        return True
    return False


hits = [n for n in distinct if tabkey(n)]
show("FINAL tabkey candidate (generated corpus)", hits)

# part (ii) alone, to see what it adds
def part2(n):
    ts = toks(n)
    return len(ts) >= 6 and any(
        c >= 3 and len(t) <= 5 and t[:1].isupper() and t.isalpha()
        for t, c in Counter(ts).items()
    )

show("part (ii) alone", [n for n in distinct if part2(n)])
print("\nTARGET tabkey():", tabkey(TARGET))
for control in (
    "Death Manipulation",
    "Regeneration (Low-Mid)",
    "Straw Doll Technique: Resonance",
    "Soul Physiology & Hollow Physiology (Soul: High-Tier Arrancar)",
    "Enhanced Senses (Telescopic Vision, Microscopic Vision, Super Hearing)",
    "Chaos Energy Manipulation & Space-Time Manipulation",
):
    print("control", repr(control), "->", tabkey(control))
