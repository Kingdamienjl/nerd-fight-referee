#!/usr/bin/env python3
"""Frag-8 calibration round 2 (read-only): revised v2 rules.

- Disclaimer rule A/B: print FULL texts of every hit (hand-judge).
- Prose-sentence-shard v2: leading conjunction/preposition/curated-
  gerund openers OR trailing lead-in; spares = subject-led finite
  clause (incl. demonstrative subjects), comma+main-clause, and a
  limitation-marker spare. Per-class counts + full-text samples.
- Gerund coverage: -ing openers NOT in the curated set.
- Refined sibling-cluster: runs >=3 pieces, each >=4 words,
  continuation boundaries throughout, joined text has no limitation
  marker. Count + samples.
- Verbatim sanity: the 6 frag-8 failing items + keeps/controls under
  the v2 functions.
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

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
SUBJECTS = frozenset({
    "he", "she", "they", "we", "it", "this", "that", "these", "those",
    "i", "you", "there",
})
LIMIT_RE = re.compile(
    r"\b(weak|weakness|weaknesses|vulnerab|susceptib|allerg|immun|"
    r"intoleran|powerless|helpless|drains|drained|draining|exhaust|"
    r"fatigue|drawback|limitation|backfire|recoil|cannot|can't|unable|"
    r"ineffective|dependent|addict|fear|afraid|blind|deaf|loses|losing|"
    r"loss of|harms|hurts|damages|kills|deadly|fatal|poison|toxic|"
    r"sick|ill\b)\b",
    re.I,
)


def toks_of(text):
    return re.findall(r"[a-z]+(?:'[a-z]+)?", text.casefold())


def finite_verb(tok):
    if tok.endswith("'s"):
        return False
    return len(tok) >= 4 and tok.endswith("s") and not tok.endswith(
        ("ss", "us", "is"))


def headed(toks):
    return any(
        (t in AUX or finite_verb(t)) and i > 0
        and toks[i - 1] not in FUNCTION
        for i, t in enumerate(toks)
    )


def subject_led(toks):
    """A subject token followed within 2 tokens by AUX/finite verb."""
    for i, t in enumerate(toks):
        if t in SUBJECTS:
            for j in range(i + 1, min(i + 3, len(toks))):
                if toks[j] in AUX or finite_verb(toks[j]):
                    return True
            return False
    return False


def comma_main_clause(item):
    if "," not in item:
        return False
    return headed(toks_of(item.split(",", 1)[1])) or subject_led(
        toks_of(item.split(",", 1)[1]))


# --- disclaimer v2 (same as round 1) ---
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


def page_disclaimer(text):
    low = text.casefold()
    if not FP_RE.search(low):
        return False
    return any(rx.search(low) for rx in ATTRIBUTION_RE)


def disclaimer_b(text):
    low = text.casefold()
    return "displayed on any profile" in low or (
        "based on" in low and "solely" in low)


# --- shard v2 ---
CONJ = ("but ", "and ", "so ", "yet ", "however ", "although ",
        "though ", "rather than ")
PREP = ("during ", "after ", "before ", "with ", "without ", "by ",
        "through ", "despite ", "because of ", "due to ", "in spite of ",
        "instead of ")
GERUNDS = frozenset({
    "leading", "supplying", "using", "causing", "leaving", "making",
    "resulting", "allowing", "dealing", "creating", "being", "having",
    "meaning", "starting", "sending", "striking", "healing", "becoming",
    "attacking", "turning", "giving", "forcing", "damaging", "preventing",
    "destroying", "generating", "shielding", "blinding", "granting",
    "projecting", "spending", "summoning", "removing", "inflicting",
    "halving", "including", "showing", "taking", "putting", "keeping",
    "breaking", "cutting", "burning", "freezing", "draining", "weakening",
    "reducing", "increasing", "following", "wielding", "fighting",
    "running", "moving", "hitting", "killing", "destroying", "losing",
    "gaining", "getting", "going", "coming", "looking", "trying",
    "failing", "missing", "lacking", "needing", "wanting", "fearing",
    "suffering", "bleeding", "burning", "melting", "cracking",
})
TRAILING = ("for example", "for instance", "such as", "e.g.")


def prose_sentence_shard_v2(value):
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.casefold()
    toks = toks_of(text)
    if not toks:
        return False
    if LIMIT_RE.search(text):
        return False
    stripped = lowered.strip().lstrip("([\"'* ")
    opener = None
    for op in CONJ:
        if stripped.startswith(op):
            opener = ("conjunction", op.strip())
            break
    if opener is None:
        for op in PREP:
            if stripped.startswith(op):
                opener = ("preposition", op.strip())
                break
    if opener is None and toks[0] in GERUNDS:
        opener = ("gerund", toks[0])
    tail = re.sub(r"[.\s]+$", "", lowered.strip())
    trailing = any(tail.endswith(lead) for lead in TRAILING)
    if opener is None and not trailing:
        return False
    if headed(toks) or subject_led(toks) or comma_main_clause(text):
        return False
    return True


profiles = 0
items_total = 0
disc_a_full = []
disc_b_full = []
shard_counts = Counter()
shard_samples = {}
gerund_uncovered = Counter()
gerund_uncovered_ex = {}
cluster_runs = Counter()
cluster_ex = {}
trailing_counts = Counter()

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
    names = [str(i.get("name") or "") for i in weak
             if isinstance(i, dict)]
    # refined cluster: runs >= 3, each >= 4 words, continuation bounds
    run = [names[0]] if names else []
    def flush(run):
        if len(run) >= 3:
            joined = " ".join(run)
            if not LIMIT_RE.search(joined):
                key = joined[:100]
                cluster_runs[key] += 1
                cluster_ex.setdefault(key, str(path))
    for prev, cur in zip(names, names[1:]):
        cont = (cur and cur[:1].islower()
                or cur.casefold().startswith(
                    ("but ", "and ", "so ", "rather than ")))
        no_term = not re.search(r"[.!?]\s*$", prev.strip())
        long_enough = len(prev.split()) >= 4 and len(cur.split()) >= 4
        if cont and no_term and long_enough:
            run.append(cur)
        else:
            flush(run)
            run = [cur]
    flush(run)
    for item in weak:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        desc = str(item.get("description") or "")
        if not name:
            continue
        items_total += 1
        for label, text in (("name", name), ("desc", desc)):
            if page_disclaimer(text):
                disc_a_full.append((label, text, str(path)))
            if disclaimer_b(text):
                disc_b_full.append((label, text, str(path)))
        # shard v2 on name
        if prose_sentence_shard_v2(name):
            low = name.casefold().strip().lstrip("([\"'* ")
            klass = None
            for op in CONJ:
                if low.startswith(op):
                    klass = ("conjunction", op.strip())
                    break
            if klass is None:
                for op in PREP:
                    if low.startswith(op):
                        klass = ("preposition", op.strip())
                        break
            if klass is None:
                t0 = toks_of(name)
                if t0 and t0[0] in GERUNDS:
                    klass = ("gerund", t0[0])
            if klass is None:
                tail = re.sub(r"[.\s]+$", "", low)
                for lead in TRAILING:
                    if tail.endswith(lead):
                        klass = ("trailing", lead)
                        break
            if klass is None:
                klass = ("unknown", "?")
            shard_counts[klass] += 1
            shard_samples.setdefault(klass, []).append(
                (name, str(path)))
            if klass[0] == "trailing":
                trailing_counts[klass[1]] += 1
        else:
            t0 = toks_of(name)
            if t0 and t0[0].endswith("ing") and len(t0[0]) >= 4 \
                    and t0[0] not in GERUNDS:
                gerund_uncovered[t0[0]] += 1
                gerund_uncovered_ex.setdefault(t0[0],
                                               (name, str(path)))

print(f"profiles_scanned={profiles} weakness_items={items_total}")
print(f"\n== DISCLAIMER rule A FULL HITS: {len(disc_a_full)}")
for label, text, path in disc_a_full:
    print(f"  [{label}] {text!r}\n      @ {path}")
print(f"\n== DISCLAIMER rule B FULL HITS: {len(disc_b_full)}")
for label, text, path in disc_b_full:
    print(f"  [{label}] {text!r}\n      @ {path}")
print(f"\n== SHARD v2 TOTAL: {sum(shard_counts.values())} raw")
for klass, n in shard_counts.most_common(50):
    print(f"  {n:4d}  {klass}")
print("\n== SHARD v2 SAMPLES (up to 8 per class) ==")
for klass in sorted(shard_samples):
    print(f"  -- {klass} --")
    for name, path in shard_samples[klass][:8]:
        print(f"     {name!r}\n        @ {path}")
print(f"\n== GERUND openers NOT in curated set: "
      f"{sum(gerund_uncovered.values())} raw, "
      f"{len(gerund_uncovered)} distinct")
for g, n in gerund_uncovered.most_common(25):
    print(f"  {n:4d}  {g!r}  e.g. {gerund_uncovered_ex[g][0][:80]!r}")
print(f"\n== REFINED CLUSTER runs>=3, each>=4 words, no limitation: "
      f"{sum(cluster_runs.values())} raw, {len(cluster_runs)} distinct")
for k, n in cluster_runs.most_common(20):
    print(f"  {n:4d}  {k!r}  e.g. {cluster_ex[k]}")

print("\n== VERBATIM SANITY (v2 functions) ==")
verbatim = [
    ("carnage disclaimer (full)",
     "any information displayed on any profile based on Death Battle "
     "are solely based on whatever is said in their videos and not my "
     "own opinion. So if a character is weaker or stronger on a profile "
     "than they actually are then it isn't my fault."),
    ("carnage disclaimer (120-cap name)",
     "any information displayed on any profile based on Death Battle "
     "are solely based on whatever is said in their videos and "),
    ("darwin shard 1 (lead clause)",
     "His body will adapt to whatever means to make Darwin survive"),
    ("darwin shard 2",
     "but will not meet his desires in many situations. For example"),
    ("darwin shard 3", "during his fight with the Hulk"),
    ("darwin shard 4",
     "rather than supplying a combat-related power."),
    ("kraven shard", "leading to mistakes."),
    ("kraven keep",
     "His belief in his superior hunting abilities may cause him to "
     "underestimate opponents"),
    ("control: however + complete clause",
     "however this can be negated by just using an even bigger shield."),
    ("control: but + subject clause",
     "but he cannot fly without his cape"),
    ("control: using + finite verb",
     "Using his powers drains him quickly"),
    ("control: due-to limitation",
     "due to not having his symbol in her armor"),
    ("control: leaving vulnerable",
     "leaving him vulnerable to attack"),
    ("control: being powerless",
     "Being powerless without his ring"),
    ("control: weak to fire", "Is weak to fire"),
    ("control: sunlight", "Weakness to sunlight"),
]
for label, text in verbatim:
    print(f"  disclaimer={page_disclaimer(text) or disclaimer_b(text)} "
          f"shard={prose_sentence_shard_v2(text)}  :: {label}")
