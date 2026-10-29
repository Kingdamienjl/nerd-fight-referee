#!/usr/bin/env python3
"""Frag-9 calibration round 2b (read-only): scope the bare-NP half
of the header + cut-off screen. For colon items whose post-colon
rest is a bare NP (no finite verb, not subordinate-only), split by
the rest's opening shape and report counts + samples:
  - rest starts with "The " (definite NP, e.g. "The Venom symbiote")
  - rest starts with "A "/"An " (indefinite NP)
  - rest starts with a finite verb ("Burns on contact" -- must NOT fire)
  - rest is any other bare NP
Also: rest word-length distribution for the "The " class, and how
many "The "-class items are already caught by an existing reason.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

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


def has_finite_verb(text):
    toks = tokens_of(text)
    expanded = ar._shard_expand_contractions(toks)
    return ar._shard_headed(expanded) or ar._shard_subject_led(expanded)


classes = Counter()
samples = defaultdict(list)
the_lengths = Counter()
the_already = 0
the_total = 0

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
        m = COLON_RE.match(name.strip())
        if not m or not (1 <= len(m.group(1).split()) <= 6):
            continue
        rest = m.group(2).strip()
        low = rest.casefold()
        if spared(rest):
            continue
        if any(low.startswith(op) for op in SUBORD_OPENERS):
            continue
        if has_finite_verb(rest):
            klass = "verb_led"
        elif low.startswith("the "):
            klass = "the_np"
            the_total += 1
            the_lengths[len(rest.split())] += 1
            if ar.fragment_item_reasons(name, section="weaknesses"):
                the_already += 1
        elif low.startswith(("a ", "an ")):
            klass = "a_np"
        else:
            klass = "other_bare_np"
        classes[klass] += 1
        samples[klass].append(name[:120])

print(f"bare-NP post-colon classes: {dict(classes)}")
print(f"'The '-NP class: {the_total} total, already caught by "
      f"existing reasons: {the_already}")
print(f"'The '-NP rest word lengths: {sorted(the_lengths.items())}")
for klass in ("the_np", "a_np", "verb_led", "other_bare_np"):
    print(f"\n== {klass} ({len(samples[klass])} collected, showing 25)")
    for s in samples[klass][:25]:
        print(f"  - {s!r}")
