#!/usr/bin/env python3
"""Frag-8 calibration scan (read-only) over stored profiles.

(a) Page-disclaimer candidates in weaknesses: first-person voice +
    attribution/disclaimer language. Measure rule A (first-person AND
    attribution marker), rule B (capped-name safety: 'displayed on any
    profile' OR 'based on' + 'solely'), and the marginals.
(b) Prose-sentence-shard leading-edge candidates: items opening with a
    conjunction / preposition / gerund, or ending on a lead-in
    ('For example'). Measure per class WITH the headed-clause and
    comma+main-clause spares applied, plus the unsparing raw counts.
(c) Lead-clause pool: stored weakness items that are complete
    subject-led clauses with no limitation marker (the false-positive
    pool for any naive item-level 'lead clause' rule), and the
    sibling-cluster pattern (consecutive items chaining into one
    sentence) prevalence in stored data.
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

# --- shared helpers (mirrors of auto_repair prose helpers) ---
AUX = frozenset({
    "is", "are", "was", "were", "has", "have", "had", "can", "could",
    "will", "would", "shall", "should", "may", "might", "must", "does",
    "did", "be", "been", "being", "am",
})
FUNCTION = AUX | frozenset({
    "the", "a", "an", "this", "that", "these", "those", "to", "from",
    "with", "by", "in", "on", "at", "of", "for", "against", "into",
    "onto", "upon", "and", "or", "but", "than", "as", "so", "if",
    "when", "while", "not", "no", "sometimes", "always", "often",
    "usually", "still", "already", "even", "also", "just", "now",
    "then", "simply", "quickly",
})


def looks_like_finite_verb(token: str) -> bool:
    if token.endswith("'s"):
        return False
    return len(token) >= 4 and token.endswith("s") and not token.endswith(
        ("ss", "us", "is"))


def tokens_of(text: str) -> list:
    return re.findall(r"[a-z]+(?:'[a-z]+)?", text.casefold())


def headed(tokens: list) -> bool:
    """A finite verb/AUX preceded by a non-function token (subject-led)."""
    return any(
        (t in AUX or looks_like_finite_verb(t)) and i > 0
        and tokens[i - 1] not in FUNCTION
        for i, t in enumerate(tokens)
    )


def comma_main_clause(item: str) -> bool:
    if "," not in item:
        return False
    tail = item.split(",", 1)[1]
    return headed(tokens_of(tail))


LIMITATION = re.compile(
    r"\b(weak|weakness|vulnerab|susceptib|allerg|immun|intoleran|phobia|"
    r"poison|toxic|disease|sick|harm|hurt|damage|kill|deadly|fatal|"
    r"drains|drained|exhaust|fatigue|drawback|limitation|backfire|recoil|"
    r"cannot|can't|unable|ineffective|dependent|addict|fear|afraid|blind|"
    r"deaf|slow|stupid|naive|arrogant|pride|anger|rage|berserk|insan|"
    r"only|needs|requires|requirement|without|loses|losing|loss of|"
    r"sunlight|kryptonite|magic|lead|gold|silver|iron|wood|salt|water|fire|"
    r"cold|heat|radiation|electric|sound|light|dark)\b",
    re.I,
)

# --- (a) page disclaimer ---
FP_RE = re.compile(
    r"\b(i|my|me|we|our|us|myself|ourselves|i'm|i've|i'll|we're|we've)\b",
    re.I,
)
ATTRIBUTION = (
    "based on", "solely", "not my own", "their videos", "this page",
    "this wiki", "according to", "as stated", "in my opinion", "i think",
    "i believe", "my own", "my fault", "displayed on", "whatever is said",
    "not my fault", "isn't my", "on any profile", "their own videos",
    "the videos", "what is said",
)
ATTRIBUTION_RE = [re.compile(re.escape(p), re.I) for p in ATTRIBUTION]

# --- (b) prose sentence shard, leading edge ---
CONJ_OPENERS = (
    "but ", "and ", "so ", "yet ", "however ", "although ", "though ",
    "rather than ",
)
PREP_OPENERS = (
    "during ", "after ", "before ", "with ", "without ", "by ",
    "through ", "despite ", "because of ", "due to ", "in spite of ",
    "instead of ",
)
TRAILING_LEADIN = ("for example", "for instance", "such as", "e.g.")

profiles = 0
items_total = 0
# (a) counters
disc_a = Counter()
disc_a_ex = {}
disc_b = Counter()
disc_b_ex = {}
fp_only = Counter()
attr_only = Counter()
# (b) counters: class -> (raw, spared-out, final) keyed by opener
shard_raw = Counter()
shard_final = Counter()
shard_ex = {}
trailing_raw = Counter()
trailing_ex = {}
# (c) counters
lead_clause_pool = Counter()
lead_clause_ex = {}
cluster_runs = Counter()
cluster_ex = {}
cluster_any = 0

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    profiles += 1
    weak = prof.get("weaknesses")
    if isinstance(weak, dict):
        weak = list(weak.values())
    weak = weak or []
    # (c) sibling-cluster simulation over stored weakness items
    names = []
    for item in weak:
        if isinstance(item, dict):
            names.append(str(item.get("name") or ""))
    for i in range(len(names) - 1):
        cur, nxt = names[i], names[i + 1]
        if not cur or not nxt:
            continue
        if re.search(r"[.!?]\s*$", cur.strip()):
            continue
        if not (nxt[:1].islower() or nxt.casefold().startswith(
                ("but ", "and ", "so ", "rather than "))):
            continue
        cluster_any += 1
        run_words = len(cur.split()) + len(nxt.split())
        joined = f"{cur} {nxt}"
        jt = tokens_of(joined)
        if (run_words >= 6 and headed(jt)
                and not LIMITATION.search(joined)):
            key = joined[:90]
            cluster_runs[key] += 1
            cluster_ex.setdefault(key, str(path))
    for item in weak:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        desc = str(item.get("description") or "")
        if not name:
            continue
        items_total += 1
        lowered = name.casefold()
        # (a) on name and on description
        for label, text in (("name", name), ("desc", desc)):
            low = text.casefold()
            has_fp = bool(FP_RE.search(low))
            has_attr = [p for p, rx in zip(ATTRIBUTION, ATTRIBUTION_RE)
                        if rx.search(low)]
            if has_fp and has_attr:
                key = f"{label}::{has_attr[0]}"
                disc_a[key] += 1
                disc_a_ex.setdefault(key, f"{name[:90]!r} @ {path}")
            if "displayed on any profile" in low or (
                    "based on" in low and "solely" in low):
                key = label
                disc_b[key] += 1
                disc_b_ex.setdefault(key, f"{name[:90]!r} @ {path}")
            if has_fp and not has_attr:
                fp_only[label] += 1
            if has_attr and not has_fp:
                attr_only[label] += 1
        # (b) leading edge on name
        stripped = lowered.strip().lstrip("([\"'* ")
        opener = None
        klass = None
        for op in CONJ_OPENERS:
            if stripped.startswith(op):
                opener, klass = op.strip(), "conjunction"
                break
        if opener is None:
            for op in PREP_OPENERS:
                if stripped.startswith(op):
                    opener, klass = op.strip(), "preposition"
                    break
        toks = tokens_of(name)
        if opener is not None:
            shard_raw[(klass, opener)] += 1
            if not headed(toks) and not comma_main_clause(name):
                shard_final[(klass, opener)] += 1
                shard_ex.setdefault(
                    (klass, opener), f"{name[:90]!r} @ {path}")
        elif toks and toks[0].endswith("ing") and len(toks[0]) >= 4:
            shard_raw[("gerund", toks[0])] += 1
            if not headed(toks) and not comma_main_clause(name):
                shard_final[("gerund", toks[0])] += 1
                shard_ex.setdefault(
                    ("gerund", toks[0]), f"{name[:90]!r} @ {path}")
        tail = re.sub(r"[.\s]+$", "", lowered.strip())
        for lead in TRAILING_LEADIN:
            if tail.endswith(lead):
                trailing_raw[lead] += 1
                trailing_ex.setdefault(lead, f"{name[:90]!r} @ {path}")
        # (c) lead-clause pool: complete subject-led clause, no limitation
        if (len(toks) >= 4 and headed(toks)
                and not LIMITATION.search(name)
                and re.match(r"^[A-Z]", name.strip())):
            key = name[:80]
            lead_clause_pool[key] += 1
            lead_clause_ex.setdefault(key, str(path))

print(f"profiles_scanned={profiles} weakness_items={items_total}")
print("\n== (a) PAGE DISCLAIMER rule A (first-person AND attribution): "
      f"{sum(disc_a.values())} raw, {len(disc_a)} distinct keys")
for k, n in disc_a.most_common(30):
    print(f"  {n:4d}  {k}  e.g. {disc_a_ex[k]}")
print(f"\n== (a) PAGE DISCLAIMER rule B (displayed-on-any-profile OR "
      f"based-on+solely): {sum(disc_b.values())} raw")
for k, n in disc_b.most_common(10):
    print(f"  {n:4d}  {k}  e.g. {disc_b_ex[k]}")
print(f"\n== (a) marginals: first-person-only name={fp_only['name']} "
      f"desc={fp_only['desc']} | attribution-only name={attr_only['name']} "
      f"desc={attr_only['desc']}")
print("\n== (b) LEADING-EDGE raw hits (before spares): "
      f"{sum(shard_raw.values())} raw")
for (klass, op), n in shard_raw.most_common(40):
    print(f"  {n:4d}  [{klass}] {op!r}")
print("\n== (b) LEADING-EDGE final hits (after headed/comma spares): "
      f"{sum(shard_final.values())} raw, {len(shard_final)} distinct openers")
for (klass, op), n in shard_final.most_common(40):
    print(f"  {n:4d}  [{klass}] {op!r}  e.g. {shard_ex[(klass, op)]}")
print("\n== (b) TRAILING lead-in hits: "
      f"{sum(trailing_raw.values())} raw")
for lead, n in trailing_raw.most_common(10):
    print(f"  {n:4d}  ends {lead!r}  e.g. {trailing_ex[lead]}")
print(f"\n== (c) LEAD-CLAUSE pool (subject-led clause, no limitation "
      f"marker): {sum(lead_clause_pool.values())} raw, "
      f"{len(lead_clause_pool)} distinct")
for k, n in lead_clause_pool.most_common(25):
    print(f"  {n:4d}  {k!r}  e.g. {lead_clause_ex[k]}")
print(f"\n== (c) SIBLING-CLUSTER pattern (continuation boundary + "
      f">=6 words + headed + no limitation): {sum(cluster_runs.values())} "
      f"raw, {len(cluster_runs)} distinct; any-continuation-boundary "
      f"pairs={cluster_any}")
for k, n in cluster_runs.most_common(25):
    print(f"  {n:4d}  {k!r}  e.g. {cluster_ex[k]}")
