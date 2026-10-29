#!/usr/bin/env python3
"""Frag-9 calibration round 2 (read-only): dump hand-review samples
of the residual (post-spare) populations from calib1, so the screen
design can be judged on real items, not counts.

- (a) residual relative-pronoun openers, per pronoun (max 25 each)
- (b) residual or/even/like openers, per marker (max 25 each)
- (c) starts-with-digits(3) items (max 25); leading-zero openers
    0xx (count + max 25); ends-with-1-digit items (max 10, to show
    why no rule there)
- (d) subordinate_only colon items (max 25); bare_np colon items
    (max 25); complete colon items (max 8, controls)
"""
import re
import sys
from collections import defaultdict
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
    toks = tokens_of(name)
    expanded = ar._shard_expand_contractions(toks)
    if ar._shard_headed(expanded):
        return True
    if ar._shard_subject_led(expanded):
        return True
    if ar._shard_comma_main_clause(name):
        return True
    if ar._SHARD_LIMITATION_RE.search(name):
        return True
    return False


def show(title, samples, limit=25):
    print(f"\n== {title} ({len(samples)} collected, showing {min(limit, len(samples))})")
    for s in samples[:limit]:
        print(f"  - {s!r}")


rel = defaultdict(list)
oel = defaultdict(list)
starts3 = []
leadzero = []
ends1 = []
subord = []
barenp = []
complete = []

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    weak = prof.get("weaknesses")
    if isinstance(weak, dict):
        weak = list(weak.values())
    for item in weak or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        stripped = name.casefold().strip().lstrip("([\"'* ")
        if not spared(name):
            for pron in REL_PRONOUNS:
                if stripped.startswith(pron):
                    rel[pron.strip()].append(name[:120])
                    break
            for marker in OR_EVEN_LIKE:
                if stripped.startswith(marker):
                    oel[marker.strip()].append(name[:120])
                    break
        bare = name.strip().rstrip(".")
        if re.match(r"\d{3}\b", name.strip()):
            starts3.append(name[:120])
        if re.match(r"0\d\d\b", name.strip()):
            leadzero.append(name[:120])
        if re.search(r"\b\d\s*$", bare) and len(ends1) < 10:
            ends1.append(name[:120])
        m = COLON_RE.match(name.strip())
        if m and 1 <= len(m.group(1).split()) <= 6:
            rest = m.group(2).strip()
            low = rest.casefold()
            if spared(rest):
                if len(complete) < 8:
                    complete.append(name[:120])
            elif any(low.startswith(op) for op in SUBORD_OPENERS):
                subord.append(name[:120])
            else:
                barenp.append(name[:120])

for k in ("which", "that", "who", "whom", "whose", "what"):
    show(f"(a) residual {k!r} opener", rel.get(k, []))
for k in ("or", "even", "like"):
    show(f"(b) residual {k!r} opener", oel.get(k, []))
show("(c) starts with exactly 3 digits", starts3)
show("(c) leading-zero opener 0xx", leadzero)
show("(c) ends with 1 digit (why no rule)", ends1)
show("(d) subordinate-only post-colon", subord)
show("(d) bare-NP post-colon", barenp)
show("(d) complete post-colon (controls)", complete, limit=8)
