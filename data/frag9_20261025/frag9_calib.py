#!/usr/bin/env python3
"""Frag-9 calibration scan (read-only) over stored weakness items.

(a) Relative-pronoun openers: items opening with which/that/who/whom/
    whose/what. Measure raw per pronoun, then with the frag-8 shard
    spares applied (subject-led finite clause, comma + main clause,
    limitation marker anywhere) -- the residual is what a new screen
    would drop. Also report how many are ALREADY caught by an
    existing fragment reason.
(b) or/even/like openers: same treatment, per marker. ("or" was NOT
    in the frag-8 conjunction set; "even" is an adverb opener;
    "like" a prepositional opener.)
(c) Numeric fragments: items ending in bare digits, starting with
    digits, digits-only; sibling pairs (A ends in bare digits, B
    starts with digits) and whether the pair forms a thousands-comma
    number (A trailing run 1-3 digits, B leading run exactly 3 digits
    then a non-digit).
(d) Header + cut-off clause: items of form "Header: <rest>".
    Classify <rest>: complete (subject-led finite clause or comma +
    main clause), subordinate-only (opens As/If/When/Because/While/
    After/Before/Although/Though/Since/Unless/Once/Until with no main
    clause), bare NP (no finite verb at all). Report counts + samples
    per class, and how many are already caught by existing reasons.
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

REL_PRONOUNS = ("which ", "that ", "who ", "whom ", "whose ", "what ")
OR_EVEN_LIKE = ("or ", "even ", "like ")
SUBORD_OPENERS = (
    "as ", "if ", "when ", "because ", "while ", "after ", "before ",
    "although ", "though ", "since ", "unless ", "once ", "until ",
)
COLON_RE = re.compile(r"^(.{1,80}?):\s+(.+)$")


def tokens_of(text):
    return re.findall(r"[a-z]+(?:'[a-z]+)?", text.casefold())


def spared(name):
    """Frag-8 shard spares: complete clause / comma+main / limitation."""
    toks = tokens_of(name)
    expanded = ar._shard_expand_contractions(toks)
    if ar._shard_headed(expanded):
        return "headed"
    if ar._shard_subject_led(expanded):
        return "subject_led"
    if ar._shard_comma_main_clause(name):
        return "comma_main"
    if ar._SHARD_LIMITATION_RE.search(name):
        return "limitation"
    return None


def existing_reasons(name):
    return ar.fragment_item_reasons(name, section="weaknesses")


profiles = 0
items_total = 0

rel_raw = Counter()
rel_resid = Counter()
rel_ex = {}
rel_spare = Counter()
rel_already = Counter()

oel_raw = Counter()
oel_resid = Counter()
oel_ex = {}
oel_spare = Counter()
oel_already = Counter()

num_end = Counter()
num_end_ex = {}
num_start = Counter()
num_start_ex = {}
num_only = Counter()
num_only_ex = {}
pair_total = 0
pair_thousands = 0
pair_ex = {}
pair_thousands_ex = {}

colon_total = 0
colon_class = Counter()
colon_ex = {}
colon_already = Counter()

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    profiles += 1
    weak = prof.get("weaknesses")
    if isinstance(weak, dict):
        weak = list(weak.values())
    weak = weak or []
    names = []
    for item in weak:
        if isinstance(item, dict):
            names.append(str(item.get("name") or ""))
    # (c) sibling pairs over the profile's weakness names
    for i in range(len(names) - 1):
        a, b = names[i].strip(), names[i + 1].strip()
        if not a or not b:
            continue
        a_end = re.search(r"(\d+)\s*[.\s]*$", a)
        b_start = re.match(r"(\d+)", b)
        if a_end and b_start:
            pair_total += 1
            pair_ex.setdefault(f"{a[-40:]} | {b[:40]}", str(path))
            if len(a_end.group(1)) <= 3 and len(b_start.group(1)) == 3 and (
                len(b) == len(b_start.group(1))
                or not b[len(b_start.group(1))].isdigit()
            ):
                pair_thousands += 1
                pair_thousands_ex.setdefault(
                    f"{a[-40:]} | {b[:40]}", str(path))
    for name in names:
        if not name:
            continue
        items_total += 1
        stripped = name.casefold().strip().lstrip("([\"'* ")
        reasons = existing_reasons(name)
        # (a) relative pronoun opener
        for pron in REL_PRONOUNS:
            if stripped.startswith(pron):
                key = pron.strip()
                rel_raw[key] += 1
                rel_ex.setdefault(key, f"{name[:100]!r} @ {path}")
                if reasons:
                    rel_already[key] += 1
                sp = spared(name)
                if sp:
                    rel_spare[(key, sp)] += 1
                else:
                    rel_resid[key] += 1
                break
        # (b) or / even / like opener
        for marker in OR_EVEN_LIKE:
            if stripped.startswith(marker):
                key = marker.strip()
                oel_raw[key] += 1
                oel_ex.setdefault(key, f"{name[:100]!r} @ {path}")
                if reasons:
                    oel_already[key] += 1
                sp = spared(name)
                if sp:
                    oel_spare[(key, sp)] += 1
                else:
                    oel_resid[key] += 1
                break
        # (c) numeric fragments
        bare = name.strip().rstrip(".")
        if re.search(r"\d\s*$", bare):
            m = re.search(r"(\d+)\s*$", bare)
            key = f"ends_digits({len(m.group(1))})"
            num_end[key] += 1
            num_end_ex.setdefault(key, f"{name[:100]!r} @ {path}")
        if re.match(r"\d", name.strip()):
            m = re.match(r"(\d+)", name.strip())
            key = f"starts_digits({len(m.group(1))})"
            num_start[key] += 1
            num_start_ex.setdefault(key, f"{name[:100]!r} @ {path}")
        if re.fullmatch(r"[\d\s.,]+", name.strip()):
            num_only["digits_only"] += 1
            num_only_ex.setdefault(
                "digits_only", f"{name[:100]!r} @ {path}")
        # (d) header: rest
        m = COLON_RE.match(name.strip())
        if m and 1 <= len(m.group(1).split()) <= 6:
            colon_total += 1
            rest = m.group(2).strip()
            low = rest.casefold()
            if spared(rest):
                klass = "complete"
            elif any(low.startswith(op) for op in SUBORD_OPENERS):
                klass = "subordinate_only"
            else:
                klass = "bare_np"
            colon_class[klass] += 1
            colon_ex.setdefault(klass, f"{name[:110]!r} @ {path}")
            if reasons:
                colon_already[klass] += 1

print(f"profiles_scanned={profiles} weakness_items={items_total}")
print(f"\n== (a) RELATIVE-PRONOUN openers: raw {sum(rel_raw.values())} "
      f"residual(after spares) {sum(rel_resid.values())}")
for k, n in rel_raw.most_common():
    print(f"  {n:4d} raw  {rel_resid[k]:4d} resid  already_caught="
          f"{rel_already[k]:4d}  {k!r}  e.g. {rel_ex[k]}")
for (k, sp), n in sorted(rel_spare.items()):
    print(f"       spared {k!r} via {sp}: {n}")
print(f"\n== (b) OR/EVEN/LIKE openers: raw {sum(oel_raw.values())} "
      f"residual {sum(oel_resid.values())}")
for k, n in oel_raw.most_common():
    print(f"  {n:4d} raw  {oel_resid[k]:4d} resid  already_caught="
          f"{oel_already[k]:4d}  {k!r}  e.g. {oel_ex[k]}")
for (k, sp), n in sorted(oel_spare.items()):
    print(f"       spared {k!r} via {sp}: {n}")
print(f"\n== (c) NUMERIC fragments: ends_digits total "
      f"{sum(num_end.values())}, starts_digits total "
      f"{sum(num_start.values())}, digits_only "
      f"{sum(num_only.values())}")
for k, n in sorted(num_end.items()):
    print(f"  {n:4d}  {k}  e.g. {num_end_ex[k]}")
for k, n in sorted(num_start.items()):
    print(f"  {n:4d}  {k}  e.g. {num_start_ex[k]}")
for k, n in num_only.items():
    print(f"  {n:4d}  {k}  e.g. {num_only_ex[k]}")
print(f"  sibling digit pairs: {pair_total} total, "
      f"{pair_thousands} thousands-shaped")
for k, n in list(pair_thousands_ex.items())[:15]:
    print(f"    THOUSANDS e.g. {k!r} @ {n}")
for k, n in list(pair_ex.items())[:10]:
    print(f"    pair e.g. {k!r} @ {n}")
print(f"\n== (d) HEADER:rest items: {colon_total} total")
for k, n in colon_class.most_common():
    print(f"  {n:4d}  {k}  already_caught={colon_already[k]:4d}  "
          f"e.g. {colon_ex[k]}")
