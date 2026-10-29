"""Frag-12 calibration round 2 (read-only): refined candidate screens.
- G1: label-ONLY items (any label type) by section + needs_review split;
  label-PREFIXED items: remainder word-count + verb presence (strip rule).
- G1q: quoted title + trailing CONNECTIVE word, or quoted season/episode
  title (narrowed from calib1's over-broad pattern).
- G4a: 'Notable Attacks/Techniques:' header in weaknesses (the steven
  shape's strongest signal) + refined ability-header (exclusions,
  capability-or-2-headers).
- G4b: FULL-TEXT residual samples for hand FP judgment.
- G7: split-point shape counts (defer decision).
All counts also restricted to needs_review profiles (mass-run population).
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


LABEL_ONLY_RE = re.compile(
    r"(?i)^\s*(chapter|act|scene|part|volume|book|season|episode)\s+"
    r"(?:[ivxlcdm]+|[0-9]+)\s*[:.]?\s*$"
)
LABEL_PREFIX_RE = re.compile(
    r"(?i)^\s*(chapter|act|scene|part|volume|book|season|episode)\s+"
    r"(?:[ivxlcdm]+|[0-9]+)\b[:\.\-]?\s*(.*)$",
    re.DOTALL,
)
CONNECTIVES = {"additionally", "also", "furthermore", "however", "moreover",
               "similarly", "meanwhile", "therefore", "consequently", "instead"}
QUOTED_SEASON_RE = re.compile(r"(?i)\"[^\"]*(season|episode|finale|chapter)[^\"]*\"")
QUOTED_TAIL_RE = re.compile(r"^\s*\"[^\"]+\"\s+([A-Za-z]+)\.?\s*$")
NOTABLE_ATK_RE = re.compile(r"(?i)notable attacks(?:\s*/\s*techniques)?\s*:")
EXCLUDED_HDR = {"note", "notes", "notable", "attacks", "techniques", "weaknesses",
                "weakness", "powers", "stats", "abilities", "equipment", "see", "ref"}
ABILITY_HDR_RE = re.compile(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}):\s")
CAPABILITY_RE = re.compile(
    r"(?i)\b(can (summon|create|expand|generate|use|throw|run|fly|breathe|withstand|manipulate|transform|shoot|fire|produce|form|project|emit|control|heal|absorb|reflect)|is able to|able to)\b"
)
LIMITATION_RE = re.compile(
    r"(?i)\b(cannot|can't|can not|only|limited|weak|vulnerab|strain|lose control|loses control|unable|fail|not work|not able|restricted|prevent|suffer|susceptible|takes time|needs to|despite|however|but|afraid|fear|disadvantage|drawback|cost|drain|exhaust|risk)\b"
)
VERB_RE = re.compile(r"(?i)\b(is|are|was|were|has|have|can|could|will|would|does|did|seems|appears|shows|gives|takes|uses|allows|lets|makes|becomes|remains|fails|loses|dies|kills|attacks|defeats)\b")

stats: dict[str, Counter] = defaultdict(Counter)
g1_prefix_samples = []
g1q_samples = []
g4a_refined = []
g4b_full = []
g7_shapes = Counter()

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    rel = str(path.relative_to("/app"))
    in_nr = rel.startswith("profiles/needs_review/")
    for sec, name, desc in item_names(prof):
        val = name.strip()
        if not val:
            continue
        caught = bool(ar.fragment_item_reasons(val, section=sec))
        nr = "nr" if in_nr else "other"

        if LABEL_ONLY_RE.match(val):
            stats["g1_label_only"][f"{sec}:{nr}"] += 1
            if not caught:
                stats["g1_label_only"]["residual"] += 1
        m = LABEL_PREFIX_RE.match(val)
        if m:
            rest = (m.group(2) or "").strip()
            words = len(rest.split())
            has_verb = bool(VERB_RE.search(rest))
            key = f"words={words} verb={has_verb}"
            stats["g1_prefix_remainder"][key] += 1
            if not caught and len(g1_prefix_samples) < 15:
                g1_prefix_samples.append((rel, sec, val[:200], words, has_verb))
        qm = QUOTED_TAIL_RE.match(val)
        if qm and (qm.group(1).casefold() in CONNECTIVES or QUOTED_SEASON_RE.search(val)):
            stats["g1q_narrow"][f"{sec}:{nr}"] += 1
            if not caught:
                stats["g1q_narrow"]["residual"] += 1
                g1q_samples.append((rel, sec, val))
        if sec == "weaknesses" and NOTABLE_ATK_RE.search(val):
            stats["g4_notable_attacks"][nr] += 1
            if not caught:
                stats["g4_notable_attacks"]["residual"] += 1
        if sec == "weaknesses":
            hdrs = [h for h in ABILITY_HDR_RE.findall(val)
                    if h.split()[0].casefold() not in EXCLUDED_HDR
                    and not h.casefold().startswith("notable")]
            if hdrs and (len(hdrs) >= 2 or CAPABILITY_RE.search(val)):
                stats["g4a_refined"][nr] += 1
                if not caught:
                    stats["g4a_refined"]["residual"] += 1
                    if len(g4a_refined) < 10:
                        g4a_refined.append((rel, val, hdrs))
            if CAPABILITY_RE.search(val) and not LIMITATION_RE.search(val):
                stats["g4b_refined"][nr] += 1
                if not caught:
                    stats["g4b_refined"]["residual"] += 1
                    if len(g4b_full) < 20:
                        g4b_full.append((rel, val))
        if sec == "abilities":
            if re.search(r"\)\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}\s*(?:\(|:)", val):
                g7_shapes["paren_capitalized_label"] += 1
            if re.search(r"\)\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}\s*$", val):
                g7_shapes["paren_trailing_label"] += 1
            if "Resistance to:" in val:
                g7_shapes["resistance_colon"] += 1

for key in sorted(stats):
    print(f"{key}: {dict(stats[key])}")
print("g7_shapes:", dict(g7_shapes))
print("--- G1 prefix remainder samples (residual) ---")
for r in g1_prefix_samples:
    print(f"  {r[0]} [{r[1]}] words={r[3]} verb={r[4]} {r[2]!r}")
print("--- G1q narrow samples ---")
for r in g1q_samples[:8]:
    print(f"  {r[0]} [{r[1]}] {r[2]!r}")
print("--- G4a refined samples ---")
for r in g4a_refined:
    print(f"  {r[0]} hdrs={r[2]} {r[1][:200]!r}")
print("--- G4b FULL-TEXT samples (residual, hand-judge) ---")
for r in g4b_full:
    print(f"  == {r[0]}")
    print(f"     {r[1]!r}")
print("CALIB2 DONE")
