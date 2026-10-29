#!/usr/bin/env python3
"""Frag-10 calibration round 1 (read-only): raw populations for the
ten gate-50m weakness families, the tier backstop, the media-filename
stat screen, and the invalid-profile blast radius.

Uses the CURRENT (frag-9) code only: for each opener class, report
raw / already-caught-by-existing-screens / residual, so the new
screens can be judged on real items, not counts.
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

OPENERS = {
    "yet": ("yet ",),
    "rather": ("rather ",),
    "especially": ("especially ",),
    "to": ("to ",),
    "as": ("as ",),
    "if": ("if ",),
    "when": ("when ",),
    "because": ("because ",),
    "while": ("while ",),
    "after": ("after ",),
    "before": ("before ",),
    "since": ("since ",),
    "unless": ("unless ",),
    "once": ("once ",),
    "until": ("until ",),
    "where": ("where ",),
}
SUBORD = ("as ", "if ", "when ", "because ", "while ", "after ",
          "before ", "since ", "unless ", "once ", "until ")
LOWER_OPENERS = ("very ", "insane ", "extremely ", "highly ", "incredibly ",
                 "utterly ", "completely ", "really ", "quite ", "somewhat ",
                 "too ", "so ", "short ", "remarkably ", "notably ",
                 "particularly ", "surprisingly ", "simply ", "just ")
RATING_RE = re.compile(r"\b\d+-[A-C]\b")
QUAL_RE = re.compile(
    r"\b(?:at least|at most|likely|possibly|probably|roughly|about|"
    r"approximately|nearly|almost|far|higher|lower|much|even)\b", re.I)
MEDIA_RE = re.compile(r"\b[\w\-.]+\.(?:png|jpe?g|gif|webp|svg|bmp|tiff)\b", re.I)
DANGLING_AUX_RE = re.compile(
    r"^(?:he|she|it|they|we|you|i)\s+(?:is|are|was|were|has|have|had|can|could|"
    r"will|would|may|might|must|does|did|do)\s*$", re.I)
AGREE_RE = re.compile(
    r"\b(?:he|she|it)\s+don't\b|\b(?:they|we|you)\s+doesn't\b", re.I)


def weak_names(prof):
    weak = prof.get("weaknesses")
    if isinstance(weak, dict):
        weak = list(weak.values())
    out = []
    for item in weak or []:
        if isinstance(item, dict):
            out.append(str(item.get("name") or ""))
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
weak_items = 0
opener_raw = Counter()
opener_resid = Counter()
opener_samples = defaultdict(list)
lower_raw = Counter()
lower_samples = defaultdict(list)
multi_total = 0
final_shape = Counter()
final_samples = defaultdict(list)
agree = []
tier_total = 0
tier_norating = Counter()
tier_samples = defaultdict(list)
tier_legit = Counter()
stat_total = 0
media = []
invalid = []
invalid_other = []

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    profiles += 1
    # (F) invalid-profile blast radius
    gen = prof.get("generation") or {}
    if not prof.get("battle_eligible"):
        reasons = gen.get("ineligible_reasons")
        if reasons == []:
            invalid.append(str(path))
        elif reasons is None:
            invalid_other.append(str(path))
    names = weak_names(prof)
    weak_items += len(names)
    for name in names:
        if not name:
            continue
        low = name.casefold().strip().lstrip("([\"'* ")
        caught = bool(ar.fragment_item_reasons(name, section="weaknesses"))
        for key, ops in OPENERS.items():
            if any(low.startswith(op) for op in ops):
                opener_raw[key] += 1
                if not caught:
                    opener_resid[key] += 1
                    if len(opener_samples[key]) < 15:
                        opener_samples[key].append(name[:120])
                break
        if name[:1].islower():
            for op in LOWER_OPENERS:
                if low.startswith(op):
                    lower_raw[op.strip()] += 1
                    if len(lower_samples[op.strip()]) < 10:
                        lower_samples[op.strip()].append(name[:120])
                    break
        if AGREE_RE.search(name):
            agree.append(name[:120])
        # (B) multi-sentence items: final-sentence shape
        sentences = [s.strip() for s in re.split(r"[.!?]\s+", name.strip()) if s.strip()]
        if len(sentences) >= 2:
            multi_total += 1
            final = sentences[-1].strip().rstrip(".!?")
            flow = final.casefold()
            if DANGLING_AUX_RE.match(final):
                klass = "dangling_aux"
            elif any(flow.startswith(op) for op in SUBORD):
                klass = "subord_tail"
            elif len(final.split()) <= 3 and not re.search(
                    r"\b(?:is|are|was|were|has|have|had|can|could|will|would|"
                    r"may|might|must|does|did|do|loses|losing|weak|vulnerab)",
                    flow):
                klass = "short_no_verb_tail"
            else:
                klass = "other"
            final_shape[klass] += 1
            if klass != "other" and len(final_samples[klass]) < 15:
                final_samples[klass].append(name[:130])
    # (D/E) tier + stat corpus
    for field, text in stat_texts(prof).items():
        if not text:
            continue
        stat_total += 1
        if field == "tier":
            tier_total += 1
            if not RATING_RE.search(text):
                key = "unknown" if text.strip().casefold() in ("unknown", "varies", "n/a", "none") else "other"
                tier_norating[key] += 1
                if key == "other" and len(tier_samples["norating"]) < 25:
                    tier_samples["norating"].append(text[:130])
                if key != "other":
                    tier_legit[key] += 1
            if MEDIA_RE.search(text):
                media.append((field, text[:130]))
        elif MEDIA_RE.search(text):
            media.append((field, text[:130]))

print(f"profiles={profiles} weakness_items={weak_items} stat_values={stat_total} tier_values={tier_total}")
print("\n== (A) opener populations: raw / residual-not-caught ==")
for k in OPENERS:
    print(f"  {opener_raw[k]:5d} / {opener_resid[k]:5d}  {k}")
    for s in opener_samples[k][:8]:
        print(f"      - {s!r}")
print("\n== (A2) lowercase adverb/adjective openers (raw) ==")
for k, n in lower_raw.most_common():
    print(f"  {n:5d}  {k}")
    for s in lower_samples[k][:6]:
        print(f"      - {s!r}")
print(f"\n== (B) multi-sentence weakness items: {multi_total}; final-sentence shapes ==")
for k, n in final_shape.most_common():
    print(f"  {n:5d}  {k}")
    for s in final_samples[k][:8]:
        print(f"      - {s!r}")
print(f"\n== (C) nonstandard-agreement items: {len(agree)} ==")
for s in agree[:15]:
    print(f"  - {s!r}")
print(f"\n== (D) tier values without a rating token: {sum(tier_norating.values())} ==")
for k, n in tier_norating.most_common():
    print(f"  {n:5d}  {k}")
for s in tier_samples["norating"][:25]:
    print(f"  - {s!r}")
print(f"\n== (E) stat values with media-filename tokens: {len(media)} ==")
for f, s in media[:25]:
    print(f"  - [{f}] {s!r}")
print(f"\n== (F) invalid blast radius: ineligible_reasons==[] and not eligible: {len(invalid)}; missing reasons: {len(invalid_other)} ==")
for p in invalid[:40]:
    print(f"  - {p}")
for p in invalid_other[:10]:
    print(f"  - MISSING {p}")
