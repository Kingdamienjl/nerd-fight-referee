"""Frag-13 calibration round 3 (read-only):
- H3a-as-led: an 'as'-led subordinate clause with no finite verb and
  no auxiliary (extends the prose-shard 'as' opener past its 6-word
  cap for verb-less clauses only; the documented 'as the Attack Forme
  lowers durability' escape stays via the finite-verb test);
- H3b-verb-blocklist: name-led participial clause with a
  depicting/creating-class verb + object, no finite verb/aux;
- H2 occurrence cross-check: does every 'so far from done' line also
  carry 'i am sleepy' or 'last issue recorded'?
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar


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


AS_LED_RE = re.compile(r"^\s*as\s+", re.I)
VERB_LIST = ("creating", "depicting", "showing", "forming", "crafting", "building", "making")
VERB_RE = re.compile(
    r"^\s*(?:and\s+)?[A-Z][\w'\u2019\-]+\s+(?:[a-z]+ly\s+)?("
    + "|".join(VERB_LIST)
    + r")\s+\w+"
)


def _no_finite_verb(text):
    toks = re.findall(r"[a-z]+(?:'[a-z]+)?", text.casefold())
    if any(t in ar._PROSE_SHARD_AUX for t in toks):
        return False
    return not any(ar._looks_like_finite_verb(t) for t in toks)


def _as_led_clause(val):
    if not AS_LED_RE.match(val):
        return False
    words = len(val.split())
    if words < 3 or words > 12:
        return False
    return _no_finite_verb(val)


def _verb_blocklist(val):
    if not VERB_RE.match(val):
        return False
    return _no_finite_verb(val)


profiles = 0
items_total = 0
buckets = defaultdict(list)
caught_count = Counter()

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    profiles += 1
    rel = str(path.relative_to("/app"))
    for sec, name, desc in item_names(prof):
        items_total += 1
        val = name.strip()
        if not val:
            continue
        caught = bool(ar.fragment_item_reasons(val, section=sec))

        def add(key):
            buckets[key].append((rel, sec, val, caught))
            if caught:
                caught_count[key] += 1

        if _as_led_clause(val):
            add("h3a_as_led_verbless")
        if _verb_blocklist(val):
            add("h3b_verb_blocklist")

print(f"profiles={profiles} items={items_total}")
for key in sorted(buckets):
    v = buckets[key]
    print(f"{key}: raw={len(v)} already_caught={caught_count[key]} residual={len(v) - caught_count[key]}")
    for r in v[:12]:
        print(f"  {r[0]} [{r[1]}] caught={r[3]} {r[2][:130]!r}")
print("CALIB3 DONE")
