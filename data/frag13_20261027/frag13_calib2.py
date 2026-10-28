"""Frag-13 calibration round 2 (read-only):
- refined H3b: name-led participial clause WITH an object after the
  ing-word (escapes 2-word noun+gerund ability names like
  'Aura sensing' that killed the broad rule in round 1);
- H2/H3a against item DESCRIPTIONS as well as names (round 1 found
  them only in non-name fields);
- explicit H5 residual list.
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


SO_FAR_RE = re.compile(r"so far from done", re.I)
SLEEPY_RE = re.compile(r"\bi am sleepy\b", re.I)
LAST_ISSUE_RE = re.compile(r"last issue recorded", re.I)
SCENES_RE = re.compile(r"as the scenes depicting", re.I)
EP_HYPHEN_RE = re.compile(
    r"(?i)^\s*(season|episode|chapter|act|scene|part|volume|book)\s+"
    r"(\d+|[ivxlcdm]+)\s*[-–—]\s+"
    r"[A-Z][\w'\u2019\-]*(?:\s+[A-Z][\w'\u2019\-]*){0,4}\.?\s*$"
)
# Refined H3b: optional 'and', proper name, optional adverb, V-ing,
# at least one object word after it, no finite verb, no auxiliary.
PART_OBJ_RE = re.compile(
    r"^\s*(?:and\s+)?[A-Z][\w'\u2019\-]+\s+(?:[a-z]+ly\s+)?[a-z]+ing\s+\w+"
)


def _no_finite_verb(text):
    toks = re.findall(r"[a-z]+(?:'[a-z]+)?", text.casefold())
    if any(t in ar._PROSE_SHARD_AUX for t in toks):
        return False
    return not any(ar._looks_like_finite_verb(t) for t in toks)


def _participial_clause_obj(val):
    if not PART_OBJ_RE.match(val):
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
        for which, val in (("name", name.strip()), ("desc", desc.strip())):
            if not val:
                continue
            caught = bool(ar.fragment_item_reasons(val, section=sec))

            def add(key):
                buckets[key].append((rel, sec, which, val, caught))
                if caught:
                    caught_count[key] += 1

            if SO_FAR_RE.search(val):
                add("h2a_so_far_from_done")
            if SLEEPY_RE.search(val):
                add("h2b_i_am_sleepy")
            if LAST_ISSUE_RE.search(val):
                add("h2c_last_issue_recorded")
            if SCENES_RE.search(val):
                add("h3a_as_the_scenes")
            if which == "name" and _participial_clause_obj(val):
                add("h3b_participial_obj")
            if which == "name" and EP_HYPHEN_RE.match(val):
                add("h5_episode_hyphen_title")

print(f"profiles={profiles} items={items_total}")
for key in sorted(buckets):
    v = buckets[key]
    print(f"{key}: raw={len(v)} already_caught={caught_count[key]} residual={len(v) - caught_count[key]}")
    for r in v[:10]:
        print(f"  {r[0]} [{r[1]}|{r[2]}] caught={r[4]} {r[3][:120]!r}")
print("CALIB2 DONE")
