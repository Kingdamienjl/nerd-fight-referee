#!/usr/bin/env python3
"""Frag-7 calibration scan (read-only) over stored profiles:
1. Explicit-none family enumeration: weakness item names / profile
   weakness texts that are explicit-none statements.
2. Name-only technique candidates in weaknesses: short name-only items
   (description == name) ending in an attack-form marker noun, with no
   limitation semantics -- raw/distinct counts + samples.
3. Control pool: distinct one-word / bare-name weakness items."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

LIMITATION = re.compile(
    r"\b(weak|weakness|vulnerab|susceptib|allerg|immun|intoleran|phobia|"
    r"poison|toxic|disease|sick|ill\b|harm|hurt|damage|kill|deadly|fatal|"
    r"drains|drained|exhaust|fatigue|drawback|limitation|backfire|recoil|"
    r"cannot|can't|unable|ineffective|dependent|addict|fear|afraid|blind|"
    r"deaf|slow|stupid|naive|arrogant|pride|anger|rage|berserk|insan|"
    r"only|needs|requires|requirement|without|loses|losing|loss of|"
    r"sunlight|kryptonite|magic|lead|gold|silver|iron|wood|salt|water|fire|"
    r"cold|heat|radiation|electric|sound|light|dark)",
    re.I,
)
MARKERS = {
    "punch", "punches", "strike", "strikes", "kick", "kicks", "blast",
    "blasts", "beam", "beams", "slam", "slams", "barrage", "chop",
    "chops", "smash", "smashes", "buster", "bomber", "hammer", "fist",
    "fists", "claw", "claws", "fang", "fangs", "bite", "bites", "sting",
    "stings", "slash", "slashes", "thrust", "uppercut", "headbutt",
    "suplex", "bomb", "bombs", "cannon", "ray", "rays", "wave", "waves",
    "bolt", "bolts", "orb", "orbs", "arrow", "arrows", "spear", "spears",
    "whip", "whips", "blade", "blades", "sword", "swords",
}
NONE_HEAD = re.compile(
    r"^\s*(none\b|n/?a\b|not applicable|no known|no weaknesses|no weakness|"
    r"no notable|nothing\b|nil\b)", re.I)

items_total = 0
bare_total = 0
none_hits = Counter()
none_examples = {}
candidates = Counter()
cand_examples = {}
one_word = Counter()
profiles = 0

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    profiles += 1
    for item in prof.get("weaknesses") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        desc = str(item.get("description") or "").strip()
        if not name:
            continue
        items_total += 1
        if NONE_HEAD.match(name):
            key = name.casefold()[:60]
            none_hits[key] += 1
            none_examples.setdefault(key, str(path))
        name_only = desc == name or len(desc) <= len(name) + 2
        if name_only:
            bare_total += 1
            tokens = re.findall(r"[A-Za-z][A-Za-z'-]*", name)
            if len(tokens) == 1:
                one_word[tokens[0]] += 1
            if (
                1 <= len(tokens) <= 5
                and tokens
                and tokens[-1].casefold() in MARKERS
                and not LIMITATION.search(name)
            ):
                candidates[name] += 1
                cand_examples.setdefault(name, str(path))

print(f"profiles_scanned={profiles} weakness_items={items_total} "
      f"name_only_items={bare_total}")
print(f"\n== EXPLICIT-NONE item names: {sum(none_hits.values())} raw, "
      f"{len(none_hits)} distinct")
for key, n in none_hits.most_common(30):
    print(f"  {n:4d}  {key!r}  e.g. {none_examples[key]}")
print(f"\n== NAME-ONLY TECHNIQUE candidates: {sum(candidates.values())} raw, "
      f"{len(candidates)} distinct")
for name, n in candidates.most_common(80):
    print(f"  {n:4d}  {name!r}  e.g. {cand_examples[name]}")
print(f"\n== ONE-WORD bare weakness names: {len(one_word)} distinct")
print("  ", json.dumps(dict(one_word.most_common(60)), ensure_ascii=False))
