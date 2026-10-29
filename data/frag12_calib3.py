"""Frag-12 calibration round 3 (read-only, targeted):
- G1 prefix: stratified samples of label-prefixed items by remainder
  words (1-2, 3-5, 6-9, 10+) x verb (True/False) — to set the strip rule.
- G4b: name-vs-description — how many name-residuals are clean on the
  full description (120-char cap truncation effect).
- G4a: re-measure with extended page-structure exclusions
  (Victories/Losses/Inconclusive/Draws/Matchups/References/Discussions).
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

LABEL_PREFIX_RE = re.compile(
    r"(?i)^\s*(chapter|act|scene|part|volume|book|season|episode)\s+"
    r"(?:[ivxlcdm]+|[0-9]+)\b[:\.\-]?\s*(.*)$",
    re.DOTALL,
)
VERB_RE = re.compile(r"(?i)\b(is|are|was|were|has|have|can|could|will|would|does|did|seems|appears|shows|gives|takes|uses|allows|lets|makes|becomes|remains|fails|loses|dies|kills|attacks|defeats)\b")
EXCLUDED_HDR = {"note", "notes", "notable", "attacks", "techniques", "weaknesses",
                "weakness", "powers", "stats", "abilities", "equipment", "see", "ref",
                "victories", "losses", "inconclusive", "draws", "matchups",
                "references", "discussions", "matchup", "reference", "discussion"}
ABILITY_HDR_RE = re.compile(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}):\s")
CAPABILITY_RE = re.compile(
    r"(?i)\b(can (summon|create|expand|generate|use|throw|run|fly|breathe|withstand|manipulate|transform|shoot|fire|produce|form|project|emit|control|heal|absorb|reflect)|is able to|able to)\b"
)
LIMITATION_RE = re.compile(
    r"(?i)\b(cannot|can't|can not|only|limited|weak|vulnerab|strain|lose control|loses control|little control|no control|unable|fail|not work|not able|restricted|prevent|suffer|susceptible|takes time|needs to|despite|however|but|afraid|fear|disadvantage|drawback|cost|drain|exhaust|risk)\b"
)

def bucket(words):
    if words <= 2:
        return "1-2"
    if words <= 5:
        return "3-5"
    if words <= 9:
        return "6-9"
    return "10+"

strat: dict[tuple[str, bool], list] = defaultdict(list)
g4b_name_resid = 0
g4b_desc_clean = 0
g4a = Counter()
g4a_samples = []

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    rel = str(path.relative_to("/app"))
    for sec in ("weaknesses", "abilities", "equipment"):
        items = prof.get(sec)
        if isinstance(items, dict):
            items = list(items.values())
        for it in items or []:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "").strip()
            desc = str(it.get("description") or "").strip()
            if not name:
                continue
            m = LABEL_PREFIX_RE.match(name)
            if m:
                rest = (m.group(2) or "").strip()
                words = len(rest.split())
                has_verb = bool(VERB_RE.search(rest))
                key = (bucket(words), has_verb)
                if len(strat[key]) < 3:
                    strat[key].append((rel, sec, name[:180], words))
            if sec != "weaknesses":
                continue
            caught = bool(ar.fragment_item_reasons(name, section=sec))
            if CAPABILITY_RE.search(name) and not LIMITATION_RE.search(name) and not caught:
                g4b_name_resid += 1
                if desc and not (CAPABILITY_RE.search(desc) and not LIMITATION_RE.search(desc)):
                    g4b_desc_clean += 1
            hdrs = [h for h in ABILITY_HDR_RE.findall(name)
                    if h.split()[0].casefold() not in EXCLUDED_HDR
                    and not h.casefold().startswith("notable")]
            if hdrs and (len(hdrs) >= 2 or CAPABILITY_RE.search(name)):
                g4a["total"] += 1
                if not caught:
                    g4a["residual"] += 1
                    if len(g4a_samples) < 6:
                        g4a_samples.append((rel, name[:180], hdrs))

print(f"g4b name-residual={g4b_name_resid} of-which-desc-clean={g4b_desc_clean}")
print(f"g4a extended-exclusions: {dict(g4a)}")
for r in g4a_samples:
    print(f"  G4a: {r[0]} hdrs={r[2]} {r[1]!r}")
print("--- G1 prefix stratified samples ---")
for key in sorted(strat):
    for r in strat[key]:
        print(f"  {key} [{r[1]}] words={r[3]} {r[0]} {r[2]!r}")
print("CALIB3 DONE")
