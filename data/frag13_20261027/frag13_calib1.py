"""Frag-13 calibration round 1 (read-only): raw populations for the
H1/H2 + uncovered-quarantined debris families, against the CURRENT
(frag-12 / G-screen) code. For each candidate shape report raw /
already-caught-by-existing-screens / residual, with hand samples.
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


# ---- H1 wiki-footer instructional sentence
FOOTER_RE = re.compile(r"you can judge a person['\u2019]s power by their feats", re.I)
# ---- H2 editor note ("This profile is so far from done but i am sleepy
#      (Last issue recorded Issue #14 of Animal Man 1988)")
SO_FAR_RE = re.compile(r"so far from done", re.I)
SLEEPY_RE = re.compile(r"\bi am sleepy\b", re.I)
LAST_ISSUE_RE = re.compile(r"last issue recorded", re.I)
# ---- H3a lore-prose: subordinate "as the scenes depicting ..." clause
SCENES_RE = re.compile(r"^\s*as the scenes depicting\b", re.I)
# ---- H3b lore-prose: bare participial clause, Name + (adverb) + V-ing,
#      no finite verb anywhere, no auxiliary (a subordinate fragment
#      with no main clause: "Rhinedottir freely creating life",
#      "and Asmoday creating numerous worlds within her pocket space")
PART_HEAD_RE = re.compile(r"^\s*(?:and\s+)?[A-Z][\w'\u2019\-]+\s+(?:[a-z]+ly\s+)?[a-z]+ing\b")
# ---- H4 bare series name ("The Boys")
THE_X_RE = re.compile(r"^\s*The [A-Z][a-z]+\.?\s*$")
# ---- H5 episode title with real title, hyphen separator
#      ("Episode 2 - I'll Give You The Grand Tour") -- G1's label-title
#      rule only covers colon/dot separators.
EP_HYPHEN_RE = re.compile(
    r"(?i)^\s*(season|episode|chapter|act|scene|part|volume|book)\s+"
    r"(\d+|[ivxlcdm]+)\s*[-–—]\s+"
    r"[A-Z][\w'\u2019\-]*(?:\s+[A-Z][\w'\u2019\-]*){0,4}\.?\s*$"
)


def _no_finite_verb(text):
    toks = re.findall(r"[a-z]+(?:'[a-z]+)?", text.casefold())
    if any(t in ar._PROSE_SHARD_AUX for t in toks):
        return False
    return not any(ar._looks_like_finite_verb(t) for t in toks)


def _participial_clause(val):
    if not PART_HEAD_RE.match(val):
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
        text = name  # recovered items carry name == desc in the merge path
        val = text.strip()
        if not val:
            continue
        caught = bool(ar.fragment_item_reasons(val, section=sec))

        def add(key):
            buckets[key].append((rel, sec, val, caught))
            if caught:
                caught_count[key] += 1

        if FOOTER_RE.search(val):
            add("h1_footer_instruction")
        if SO_FAR_RE.search(val):
            add("h2a_so_far_from_done")
        if SLEEPY_RE.search(val):
            add("h2b_i_am_sleepy")
        if LAST_ISSUE_RE.search(val):
            add("h2c_last_issue_recorded")
        if SCENES_RE.match(val):
            add("h3a_as_the_scenes")
        if _participial_clause(val):
            add("h3b_participial_clause")
        if THE_X_RE.match(val):
            add("h4_the_x_bare")
        if EP_HYPHEN_RE.match(val):
            add("h5_episode_hyphen_title")

print(f"profiles={profiles} items={items_total}")
for key in sorted(buckets):
    v = buckets[key]
    print(f"{key}: raw={len(v)} already_caught={caught_count[key]} residual={len(v) - caught_count[key]}")
    for r in v[:8]:
        print(f"  {r[0]} [{r[1]}] caught={r[3]} {r[2][:120]!r}")
print("CALIB1 DONE")
