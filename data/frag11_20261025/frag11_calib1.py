#!/usr/bin/env python3
"""Frag-11 calibration round 1 (read-only): raw populations for the six
gate-50n debris families + revision-metadata prevalence (workstream B).
Uses the CURRENT (frag-10) code only: for each shape report raw /
already-caught-by-existing-screens / residual, with hand samples.
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

profiles = 0
needs_review = 0
# ---- B: revision metadata prevalence
rev_any = Counter()   # key: needs_review? -> count profiles with >=1 rev source
rev_none = Counter()
src_total = Counter()
src_rev = Counter()

# ---- F1 label bleed
LABELS = ["attack potency", "lifting strength", "striking strength",
          "standard equipment", "intelligence", "speed", "durability",
          "stamina", "range", "tier", "classification", "origin"]
LABEL_RE = {lab: re.compile(rf"(?<![a-z]){re.escape(lab)}\s*:", re.I) for lab in LABELS}
LABEL_ANY_RE = {lab: re.compile(rf"(?<![a-z]){re.escape(lab)}\b", re.I) for lab in LABELS}
f1_raw = []
f1_1label = []
f1_nocolon_multi = []

# ---- F2 ID types
ID_BARE_RE = re.compile(r"(?i)^\s*[a-z][a-z '\-]*\bid types?\s*$")
ID_ANY_RE = re.compile(r"(?i)\bid types?\b")
ID_CONTAINS_RE = re.compile(r"(?i)\bid\b")
f2_bare = []
f2_any = []
f2_contains = []

# ---- F3 headers as items
BASELINE_RE = re.compile(r"\(\s*\d+\s*-?[A-D]?\s*-\s*Baseline\s*\)", re.I)
ABIL_HDR_RE = re.compile(r"(?i)\babilities\s*\(")
f3_baseline = []
f3_abilhdr = []
name_eq_desc_total = 0
name_eq_desc_samples = []

# ---- F4 truncation proxy (filled after vocab build)
# ---- F5 bare proper name
single_token = Counter()
single_token_profiles = defaultdict(set)

# ---- F6
CONJ_LEAD = ("but ", "yet ", "so ", "nor ", "and ", "or ")
f6i = defaultdict(list)
TAIL_RE = re.compile(r"(?i)^(he|she|it|they)\s+(was|were|is|are|has|have|had)\s+([a-z]+(ed|en))\s*[.!]?\s*$")
f6ii = []
f6ii_long = []
HEAD2_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
f6iii = []
f6iii_amp = []
f6iii_he = []
FEATS_RE = re.compile(r"(?i)\bfeats\s*:")
f6iv_feats = []
f6iv_baseline = []
HDR_MARK_RE = re.compile(r"(?i)\b(?:resistances?|weaknesses?|abilities|notable attacks|standard equipment)\s*\(")
f6iv_hdr = []

# first pass: collect profiles, vocab words, single-token names
all_words = Counter()
item_list = []  # (rel, sec, name, desc)
for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    profiles += 1
    rel = str(path.relative_to("/app"))
    is_nr = rel.startswith("profiles/needs_review/")
    if is_nr:
        needs_review += 1
    srcs = [s for s in (prof.get("sources") or []) if isinstance(s, dict)]
    src_total[is_nr] += len(srcs)
    has_rev = any(s.get("source_type") == "mediawiki" and s.get("revision_id") and s.get("revision_timestamp") for s in srcs)
    src_rev[is_nr] += sum(1 for s in srcs if s.get("source_type") == "mediawiki" and s.get("revision_id") and s.get("revision_timestamp"))
    (rev_any if has_rev else rev_none)[is_nr] += 1
    # F1
    for field, val in stat_texts(prof).items():
        if not val:
            continue
        hits = [lab for lab, rx in LABEL_RE.items() if rx.search(val)]
        if len(hits) >= 2:
            # residual?
            caught = bool(ar.stat_field_rejection_reasons(val)) or bool(ar.fragment_scalar_reasons(val))
            f1_raw.append((rel, field, val, hits, caught))
        elif len(hits) == 1:
            if len(f1_1label) < 400:
                f1_1label.append((rel, field, val, hits))
        else:
            anyhits = [lab for lab, rx in LABEL_ANY_RE.items() if rx.search(val)]
            if len(anyhits) >= 2:
                f1_nocolon_multi.append((rel, field, val, anyhits))
    for sec, name, desc in item_names(prof):
        item_list.append((rel, sec, name, desc))
        for w in re.findall(r"[A-Za-z]+", (name + " " + desc)):
            all_words[w.casefold()] += 1
        # F2
        if ID_BARE_RE.match(name.strip().rstrip(".")):
            f2_bare.append((rel, sec, name))
        if ID_ANY_RE.search(name):
            f2_any.append((rel, sec, name))
        elif ID_CONTAINS_RE.search(name):
            f2_contains.append((rel, sec, name))
        # F3
        if BASELINE_RE.search(name):
            f3_baseline.append((rel, sec, name, name == desc))
        if ABIL_HDR_RE.search(name):
            f3_abilhdr.append((rel, sec, name))
        if name and name == desc:
            name_eq_desc_total += 1
            if len(name_eq_desc_samples) < 300:
                name_eq_desc_samples.append((rel, sec, name))
        # F5
        toks = name.strip().rstrip(".:!").split()
        if len(toks) == 1 and toks[0][:1].isupper() and toks[0].isalpha():
            single_token[toks[0]] += 1
            single_token_profiles[toks[0]].add(rel)
        # F6i
        stripped = name.strip().lstrip("([{\"'* ")
        low = stripped.casefold()
        for opener in CONJ_LEAD:
            if low.startswith(opener):
                f6i[opener.strip()].append((rel, sec, name))
                break
        # F6ii
        m = TAIL_RE.match(name.strip())
        if m:
            f6ii.append((rel, sec, name))
        elif re.match(r"(?i)^(he|she|it|they)\s+(was|were|is|are)\s+\w+", name.strip()) and len(name.strip().split()) <= 8:
            f6ii_long.append((rel, sec, name))
        # F6iii
        if " & " in name and not SENT_SPLIT.split(name.strip()):
            pass
        sents = [s for s in SENT_SPLIT.split(name.strip()) if s.strip()]
        if " & " in name:
            f6iii_amp.append((rel, sec, name))
        if len(sents) >= 2:
            heads = [HEAD2_RE.match(s.strip()) for s in sents]
            he_heads = sum(1 for s in sents if re.match(r"(?i)^(he|she|it|they|is|are|was|can|could)\b", s.strip()))
            if sum(1 for h in heads if h) >= 2:
                f6iii.append((rel, sec, name))
            elif he_heads >= 2:
                f6iii_he.append((rel, sec, name))
        # F6iv
        if FEATS_RE.search(desc) or FEATS_RE.search(name):
            f6iv_feats.append((rel, sec, name, desc[:160]))
        if BASELINE_RE.search(desc):
            f6iv_baseline.append((rel, sec, name, desc[:160]))
        if HDR_MARK_RE.search(desc):
            f6iv_hdr.append((rel, sec, name, desc[:160]))

print(f"profiles={profiles} needs_review={needs_review} items={len(item_list)}")
print(f"B rev: needs_review with>=1rev={rev_any[True]} without={rev_none[True]} | all with={rev_any[True]+rev_any[False]} without={rev_none[True]+rev_none[False]}")
print(f"B rev sources: needs_review rev_src={src_rev[True]}/{src_total[True]} all rev_src={src_rev[True]+src_rev[False]}/{src_total[True]+src_total[False]}")
print(f"F1 label_bleed raw(>=2 labels w/ colon)={len(f1_raw)} already_caught={sum(1 for r in f1_raw if r[4])} residual={sum(1 for r in f1_raw if not r[4])}")
for r in f1_raw[:15]:
    print("  F1:", r[0], r[1], repr(r[2][:130]), "labels=", r[3], "caught=", r[4])
print(f"F1 one-label sample n={len(f1_1label)} (controls); multi-label-no-colon n={len(f1_nocolon_multi)}")
for r in f1_1label[:8]:
    print("  F1-1lab:", r[0], r[1], repr(r[2][:110]))
for r in f1_nocolon_multi[:8]:
    print("  F1-nocolon:", r[0], r[1], repr(r[2][:110]), r[3])
print(f"F2 bare ID Types={len(f2_bare)} any-ID-Type={len(f2_any)} contains-ID-other={len(f2_contains)}")
for r in f2_bare[:15]:
    print("  F2-bare:", r)
for r in f2_contains[:10]:
    print("  F2-contains-ID:", r)
print(f"F3 baseline-pattern names={len(f3_baseline)} name==desc among them={sum(1 for r in f3_baseline if r[3])} abilities-hdr={len(f3_abilhdr)} name==desc total={name_eq_desc_total}")
for r in f3_baseline[:15]:
    print("  F3:", r[0], r[1], repr(r[2]), "eqdesc=", r[3])
for r in f3_abilhdr[:10]:
    print("  F3-abilhdr:", r)
print("  F3 name==desc legit samples:", [s[2] for s in name_eq_desc_samples[:20]])
print(f"F5 single-token ability names: distinct={len(single_token)} total_items={sum(single_token.values())}")
print("  F5 top40:", single_token.most_common(40))
hapax = [w for w, c in single_token.items() if c == 1]
print(f"  F5 hapax(single occurrence)={len(hapax)} sample:", sorted(hapax)[:40])
# profile-name cross-check
prof_names = set()
for path in Path("/app/profiles").rglob("*.yaml"):
    stem = path.stem
    prof_names.add(stem.replace("-", " ").casefold())
    prof_names.add(stem.casefold())
f5_cast = [w for w in single_token if w.casefold() in prof_names]
print(f"  F5 single-token names matching a profile file-stem={len(f5_cast)} sample:", sorted(f5_cast)[:30])
vocab5 = {w for w, c in single_token.items() if c >= 5}
print(f"  F5 vocab freq>=5 size={len(vocab5)} coverage of single-token items={sum(c for w,c in single_token.items() if w in vocab5)}/{sum(single_token.values())}")
vocab3 = {w for w, c in single_token.items() if c >= 3}
print(f"  F5 vocab freq>=3 size={len(vocab3)} coverage={sum(c for w,c in single_token.items() if w in vocab3)}/{sum(single_token.values())}")
for k, v in sorted(f6i.items()):
    print(f"F6i leading {k!r}: n={len(v)} sample:", [x[2] for x in v[:8]])
print(f"F6ii bare subj+aux+participle items={len(f6ii)} longer-subj-aux items={len(f6ii_long)}")
for r in f6ii[:15]:
    print("  F6ii:", r)
for r in f6ii_long[:10]:
    print("  F6ii-long:", r)
print(f"F6iii >=2 sentences w/ >=2 ability-head sentences={len(f6iii)} &-joined={len(f6iii_amp)} he-headed multi={len(f6iii_he)}")
for r in f6iii[:15]:
    print("  F6iii:", r[0], r[1], repr(r[2][:200]))
for r in f6iii_amp[:5]:
    print("  F6iii-amp(control):", r)
for r in f6iii_he[:5]:
    print("  F6iii-he(control):", r)
print(f"F6iv Feats: in name/desc={len(f6iv_feats)} Baseline) in desc={len(f6iv_baseline)} section-hdr-marker in desc={len(f6iv_hdr)}")
for r in f6iv_feats[:10]:
    print("  F6iv-feats:", r[0], r[1], repr(r[2][:90]), repr(r[3][:120]))
for r in f6iv_baseline[:10]:
    print("  F6iv-baseline:", r[0], r[1], repr(r[2][:90]), repr(r[3][:120]))
for r in f6iv_hdr[:10]:
    print("  F6iv-hdr:", r[0], r[1], repr(r[2][:90]), repr(r[3][:120]))
# F4 truncation proxy: final token of item name
word_vocab = {w for w, c in all_words.items() if c >= 2}
by4 = defaultdict(set)
for w in word_vocab:
    if len(w) >= 6:
        by4[w[:4]].add(w)
f4_cand = []
f4_total_paren = 0
for rel, sec, name, desc in item_list:
    n = name.strip()
    if n.endswith(")"):
        f4_total_paren += 1
    toks = re.findall(r"[A-Za-z]+", n)
    if not toks:
        continue
    last = toks[-1].casefold()
    if len(last) < 4 or last in word_vocab:
        continue
    # strict prefix of a longer vocab word?
    cands = [w for w in by4.get(last[:4], ()) if w.startswith(last) and len(w) >= len(last) + 2]
    if cands:
        f4_cand.append((rel, sec, name, last, sorted(cands)[:3]))
print(f"F4 trailing-paren items={f4_total_paren} truncated-final-token candidates={len(f4_cand)}")
for r in f4_cand[:25]:
    print("  F4:", r[0], r[1], repr(r[2]), "last=", r[3], "expansions=", r[4])
