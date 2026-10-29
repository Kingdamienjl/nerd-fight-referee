#!/usr/bin/env python3
"""Frag-11 calibration round 1b (read-only follow-ups to calib1).
(a) F1 residual-5 + stat-label-only recount; (b) F6i <=8-word counts;
(c) F4 <120 candidates + same-item-prefix subset; (d) ability-name word
frequencies (head words + terminal words) for the F4b/F6iii sets;
(e) F5 vocab freq>=2 + pinned controls; (f) F3 broader baseline
pattern; (g) F2 colon-form already-caught check; (h) F6iii refined
rule prototype counts.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

STAT_LABELS = ["attack potency", "lifting strength", "striking strength",
               "standard equipment", "intelligence", "speed", "durability",
               "stamina", "range", "tier"]
STAT_RE = {lab: re.compile(rf"(?<![a-z]){re.escape(lab)}\s*:", re.I) for lab in STAT_LABELS}

def stat_texts(prof):
    ps = prof.get("power_scale") or {}
    out = {}
    if isinstance(ps, dict):
        for field, val in ps.items():
            if isinstance(val, dict):
                out[field] = str(val.get("text") or "")
            elif isinstance(val, str):
                out[field] = val
    return out

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

f1_resid = []
f1_stat_raw = []
f6i_short = defaultdict(list)
f4_short = []
f4a = []
head_words = Counter()
terminal_words = Counter()
single_token = Counter()
baseline_broad = []
for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    rel = str(path.relative_to("/app"))
    for field, val in stat_texts(prof).items():
        if not val:
            continue
        hits = [lab for lab, rx in STAT_RE.items() if rx.search(val)]
        if len(hits) >= 2:
            caught = bool(ar.stat_field_rejection_reasons(val)) or bool(ar.fragment_scalar_reasons(val))
            f1_stat_raw.append((rel, field, val, hits, caught))
            if not caught:
                f1_resid.append((rel, field, val, hits))
    for sec, name, desc in item_names(prof):
        # F6i short
        stripped = name.strip().lstrip("([{\"'* ")
        low = stripped.casefold()
        words = len(re.findall(r"[a-z0-9]+(?:'[a-z]+)?", low))
        for opener in ("but ", "yet ", "so ", "nor ", "and ", "or "):
            if low.startswith(opener) and words <= 8:
                f6i_short[opener.strip()].append((rel, sec, name))
                break
        # F3 broad
        if re.search(r"\(\s*\d+\s*-?\s*[A-D]?\s*-\s*Baseline\b", name):
            baseline_broad.append((rel, sec, name))
        # F4 short + F4a
        toks = re.findall(r"[A-Za-z]+", name)
        if toks:
            last = toks[-1].casefold()
            if len(name) < 120 and len(last) >= 4:
                # non-word prefix check needs vocab; approximate with
                # same-item prefix (F4a) + record all short finals
                others = [t.casefold() for t in toks[:-1]]
                if any(o.startswith(last) and len(o) >= len(last) + 2 for o in others):
                    f4a.append((rel, sec, name, last))
        # ability head/terminal words (abilities section only)
        if sec == "abilities" and name:
            w = re.findall(r"[A-Za-z]+", name)
            if w:
                head_words[w[0].casefold()] += 1
                # terminal word of the head phrase (before any paren)
                head_part = name.split("(")[0].strip()
                hw = re.findall(r"[A-Za-z]+", head_part)
                if len(hw) >= 2:
                    terminal_words[hw[-1].casefold()] += 1
        toks1 = name.strip().rstrip(".:!").split()
        if len(toks1) == 1 and toks1[0][:1].isupper() and toks1[0].isalpha():
            single_token[toks1[0]] += 1

print(f"F1 stat-label-only raw(>=2)={len(f1_stat_raw)} already_caught={sum(1 for r in f1_stat_raw if r[4])} residual={len(f1_stat_raw)-sum(1 for r in f1_stat_raw if r[4])}")
for r in f1_stat_raw:
    if not r[4]:
        print("  F1-RESID:", r[0], r[1], repr(r[2][:150]), "labels=", r[3])
for r in f1_stat_raw[:10]:
    print("  F1-stat:", r[0], r[1], repr(r[2][:120]), "labels=", r[3], "caught=", r[4])
for k, v in sorted(f6i_short.items()):
    print(f"F6i-short leading {k!r} (<=8 words): n={len(v)} sample:", [x[2][:100] for x in v[:8]])
print(f"F3 broad baseline pattern (no closing paren needed): n={len(baseline_broad)}")
for r in baseline_broad:
    print("  F3-broad:", r[0], r[1], repr(r[2][:120]))
print(f"F4a same-item-prefix short items: n={len(f4a)}")
for r in f4a[:20]:
    print("  F4a:", r[0], r[1], repr(r[2][:120]), "last=", r[3])
print("F5 vocab freq>=2 size:", len([w for w, c in single_token.items() if c >= 2]),
      "coverage:", sum(c for w, c in single_token.items() if c >= 2), "/", sum(single_token.values()))
for w in ("Immortality", "Flight", "Magic", "Radagon"):
    print(f"  F5 {w}: freq={single_token.get(w, 0)}")
print("ABILITY head-word top60:", head_words.most_common(60))
print("ABILITY terminal-word top60:", terminal_words.most_common(60))
print("F2 colon-form check:")
for t in ("Fairy ID Type:", "Battle ID Type:", "Fairy ID Types", "Battle ID Types"):
    print(f"  {t!r} -> {ar.fragment_item_reasons(t)}")
print("F6iii refined prototype:")
OP_NOUNS = {"manipulation", "negation", "creation", "destruction", "control",
            "physiology", "projection", "generation", "absorption", "resistance",
            "immunity", "nullification", "erasure", "sealing", "summoning",
            "teleportation", "telekinesis", "telepathy", "clairvoyance",
            "precognition", "regeneration", "immortality", "invulnerability",
            "intangibility", "invisibility", "duplication", "shapeshifting",
            "transformation", "transmutation", "possession", "empowerment",
            "amplification", "reduction", "mimicry", "bending", "kinesis",
            "analysis", "perception", "awareness", "sensing", "travel"}
def _glued_refined(value):
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", value.strip()) if s.strip()]
    if len(sents) < 2:
        return False
    good = 0
    for s in sents:
        toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", s)
        if len(toks) < 5:
            continue
        if not (toks[0][:1].isupper() and toks[1][:1].isupper()):
            continue
        if toks[1].casefold() not in OP_NOUNS and toks[0].casefold() not in OP_NOUNS:
            continue
        good += 1
    return good >= 2
n_ref = 0
samples = []
n_items = 0
for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    for sec, name, desc in item_names(prof):
        n_items += 1
        if _glued_refined(name):
            n_ref += 1
            if len(samples) < 20:
                samples.append((str(path.relative_to("/app")), sec, name[:200]))
print(f"  refined glued-composite hits={n_ref} / {n_items} items")
for s in samples:
    print("   -", s[0], s[1], repr(s[2]))
print("  verbatim check:", _glued_refined("Durability Negation Destined Death lowers and burns HP. Death Manipulation Maliketh could manipulate Death"))
print("  control Soul&Energy:", _glued_refined("Soul Manipulation & Energy Manipulation (With the Grand Wave and Glow Soul)"))
print("  control Sound:", _glued_refined("Sound Manipulation Maliketh's roars can damage and knock down the player."))
print("  control BFR:", _glued_refined("Dimensional BFR (Can send others to Astral Chaos. All Souls taken by Soul Edge are sent to Astral Chaos."))
print("  control Searing:", _glued_refined("and Ground-type attacks. Searing Sunraze Smash can only be used once per battle. Flare Blitz and Wild Charge cause recoil"))
print("CALIB1B DONE")
