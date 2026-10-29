"""Frag-12 calibration round 1 (read-only): raw populations for the
frag-11-quarantine debris families + glue composites + placeholder,
against the CURRENT (frag-11) code. For each candidate shape report
raw / already-caught-by-existing-screens / residual, with hand samples.
Corpus: all stored profiles under /app/profiles.
"""
import json
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


# ---- G1 label/header fragments
CHAPTER_ACT_RE = re.compile(r"(?i)^\s*(chapter|act|scene|part|volume|book)\s+[ivxlcdm0-9]+\b")
SEASON_EP_RE = re.compile(r"(?i)^\s*(season|episode)\s+\d+\b")
QUOTED_TITLE_TAIL_RE = re.compile(r"^\s*\"[^\"]+\"\s+\w+\.?$")
LABEL_ONLY_RE = re.compile(r"(?i)^\s*(season|episode)\s+\d+\s*$")
# ---- G2 list-intro
HAS_FOLLOWING_RE = re.compile(r"(?i)\b\w+\s+has the following\b")
# ---- G3 bare equipment fragment (possessive + equipment noun, nothing else)
EQUIP_NOUNS = {
    "whip", "sword", "blade", "shield", "armor", "armour", "gun", "staff",
    "bow", "hammer", "dagger", "spear", "axe", "katana", "scythe", "wand",
    "rifle", "pistol", "knife", "claws", "gauntlet", "helmet", "boots",
    "cloak", "ring", "amulet", "orb", "lance", "mace", "flail", "whips",
    "swords", "blades", "shields", "guns",
}
EQUIP_RE = re.compile(r"(?i)^\s*[A-Z][\w'’-]+'s\s+(?:upgraded\s+|new\s+|enchanted\s+)?([a-z]+(?:\s+[a-z]+){0,2})\.?\s*$")
# ---- G4 wrong-section powers passage
ABILITY_HDR_RE = re.compile(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}:\s")
CAPABILITY_RE = re.compile(
    r"(?i)\b(can (summon|create|expand|generate|use|throw|run|fly|breathe|withstand|manipulate|transform|shoot|fire|produce|form|project|emit|control|heal|absorb|reflect)|is able to|able to|able to withstand|can summon)\b"
)
LIMITATION_RE = re.compile(
    r"(?i)\b(cannot|can't|can not|only|limited|weak|vulnerab|strain|lose control|loses control|unable|fail|not work|not able|restricted|prevent|suffer|susceptible|takes time|needs to|despite|however|but)\b"
)
# ---- G5 placeholder
PLACEHOLDER_RE = re.compile(r"(?i)^\s*(none\s+(noted|listed|known)|n/?a\.?|unknown|none)\.?\s*$")
# ---- G6 long and-led
AND_LED_RE = re.compile(r"(?i)^\s*and\s+\w+")
# ---- G7 glue composites
PAREN_GLUE_RE = re.compile(r"\)\s+[A-Z][A-Za-z]+")
RESIST_LIST_RE = re.compile(r"(?i)resistance to [^,]+,\s*resistance to")

profiles = 0
items_total = 0
buckets: dict[str, list] = defaultdict(list)
caught_count: dict[str, int] = Counter()
g6_long_and = []
g6_long_and_weak = []

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
        text = name  # recovered items carry name == desc in the merge path
        val = text.strip()
        if not val:
            continue
        caught = bool(ar.fragment_item_reasons(val, section=sec))
        def add(key):
            buckets[key].append((rel, sec, val, caught))
            if caught:
                caught_count[key] += 1
        if CHAPTER_ACT_RE.search(val):
            add("g1_chapter_act")
        if SEASON_EP_RE.search(val):
            add("g1_season_ep")
        if LABEL_ONLY_RE.match(val):
            add("g1_label_only")
        if QUOTED_TITLE_TAIL_RE.match(val):
            add("g1_quoted_title_tail")
        if sec == "weaknesses" and HAS_FOLLOWING_RE.search(val):
            add("g2_has_following")
        if sec == "weaknesses":
            m = EQUIP_RE.match(val)
            if m and m.group(1).strip().split()[-1] in EQUIP_NOUNS:
                add("g3_equipment")
        if sec == "weaknesses" and ABILITY_HDR_RE.search(val):
            add("g4a_ability_header")
        if sec == "weaknesses" and CAPABILITY_RE.search(val) and not LIMITATION_RE.search(val):
            add("g4b_capability_no_limitation")
        if PLACEHOLDER_RE.match(val):
            add("g5_placeholder")
        if AND_LED_RE.match(val):
            words = len(val.split())
            if words > 8:
                g6_long_and.append((rel, sec, val, caught))
                if sec == "weaknesses":
                    g6_long_and_weak.append((rel, sec, val, caught))
        if sec == "abilities" and PAREN_GLUE_RE.search(val):
            add("g7_paren_glue")
        if sec == "abilities" and RESIST_LIST_RE.search(val):
            add("g7_resist_list")

print(f"profiles={profiles} items={items_total}")
for key in sorted(buckets):
    v = buckets[key]
    print(f"{key}: raw={len(v)} already_caught={caught_count[key]} residual={len(v)-caught_count[key]}")
    for r in v[:6]:
        print(f"  {r[0]} [{r[1]}] caught={r[3]} {r[2][:120]!r}")
print(f"g6 long and-led (>8w) all-sections={len(g6_long_and)} weaknesses={len(g6_long_and_weak)}")
for r in g6_long_and_weak[:10]:
    print(f"  G6-weak: {r[0]} caught={r[3]} {r[2][:130]!r}")
for r in [x for x in g6_long_and if x[1] != "weaknesses"][:5]:
    print(f"  G6-other: {r[0]} [{r[1]}] {r[2][:130]!r}")
print("CALIB1 DONE")
