"""Frag-12 baseline (read-only): run the CURRENT fragment screens over
every corpus item and report caught vs missed, per profile/section.
An item is 'caught' if fragment_item_reasons(name) or
fragment_item_reasons(desc) returns any reason (the merge path checks
the item as a whole; name and desc are the same string for most
recovered items, but check both to be safe).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

CORPUS = Path("/app/data/frag12_20261025/corpus.json")
OUT = Path("/app/data/frag12_20261025/baseline.json")

corpus = json.loads(CORPUS.read_text())
rows = []
for rel, items in sorted(corpus.items()):
    for it in items:
        sec = it["section"]
        section = sec if sec in ("weaknesses", "abilities", "equipment", "resistances", "summons") else None
        r_name = ar.fragment_item_reasons(it["name"], section=section)
        r_desc = ar.fragment_item_reasons(it["desc"], section=section)
        reasons = sorted(set(r_name) | set(r_desc))
        rows.append({
            "profile": rel.split("/")[-1],
            "rel": rel,
            "section": sec,
            "name": it["name"],
            "desc": it["desc"],
            "caught": bool(reasons),
            "reasons": reasons,
        })

OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
from collections import Counter
c = Counter((r["profile"], r["section"], r["caught"]) for r in rows)
print("total:", len(rows), "caught:", sum(1 for r in rows if r["caught"]),
      "missed:", sum(1 for r in rows if not r["caught"]))
for (prof, sec, caught), n in sorted(c.items()):
    print(f"  {prof} [{sec}] {'CAUGHT' if caught else 'missed'}: {n}")
print("WROTE", OUT)
