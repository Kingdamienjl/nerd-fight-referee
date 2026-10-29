"""Frag-12 verbatim corpus extraction (read-only).

Parses the frag-11 cohort audit log MERGE lines for the target profiles
and writes the recorded (audit-truncated, ~80 chars) item texts to
/app/data/frag12_20261025/corpus.json. The audit logger truncates
name/desc at 80 chars, so corpus strings are verbatim-as-recorded, not
the full parser output; each entry is flagged truncated_at_80.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

LOG_DIR = Path("/app/data/frag11_20261025")
OUT_DIR = Path("/app/data/frag12_20261025")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = {
    # quarantined shape
    "profiles/needs_review/recentchanges/unknown/asmoday.yaml",
    "profiles/needs_review/recentchanges/unknown/ronova.yaml",
    "profiles/needs_review/mixed/the-boys/soldier-boy.yaml",
    "profiles/needs_review/mixed/the-boys/black-noir.yaml",
    "profiles/needs_review/mixed/the-boys/starlight.yaml",
    "profiles/needs_review/mixed/the-boys/stormfront.yaml",
    "profiles/needs_review/mixed/invincible/omni-man.yaml",
    "profiles/needs_review/mixed/steven-universe/amethyst.yaml",
    "profiles/needs_review/mixed/steven-universe/steven-universe.yaml",
    # placeholder
    "profiles/needs_review/game/street-fighter/cammy.yaml",
    # whole-section glue candidates
    "profiles/needs_review/mixed/invincible/robot.yaml",
    "profiles/needs_review/mixed/the-owl-house/hunter.yaml",
    "profiles/needs_review/game/hades/zagreus.yaml",
    "profiles/needs_review/mixed/invincible/battle-beast.yaml",
    "profiles/needs_review/tv-movie/star-wars/darth-vader.yaml",
    "profiles/needs_review/tv-movie/star-wars/general-grievous.yaml",
    "profiles/needs_review/game/mega-man/duo.yaml",
    "profiles/needs_review/game/mega-man/sigma.yaml",
}

# MERGE: <rel> [<section>] name='...' desc='...' <- [...]
MERGE_RE = re.compile(
    r"^MERGE: (\S+) \[([^\]]+)\] name='(.*)' desc='(.*)' <- \["
)
# stat lines: MERGE: <rel> [stat:<field>] <text> <- [...]
STAT_RE = re.compile(r"^MERGE: (\S+) \[stat:([^\]]+)\] (.*) <- \[")

corpus: dict[str, list[dict]] = defaultdict(list)
for log in sorted(LOG_DIR.glob("audit_cohort11*.log")):
    for line in log.read_text(errors="replace").splitlines():
        m = MERGE_RE.match(line)
        if m:
            rel, section, name, desc = m.groups()
            if rel in TARGETS:
                corpus[rel].append({
                    "section": section,
                    "name": name,
                    "desc": desc,
                    "truncated_at_80": len(name) >= 80 or len(desc) >= 80,
                })
            continue
        m = STAT_RE.match(line)
        if m:
            rel, field, text = m.groups()
            if rel in TARGETS:
                corpus[rel].append({
                    "section": f"stat:{field}",
                    "name": text,
                    "desc": text,
                    "truncated_at_80": len(text) >= 80,
                })

out = {rel: items for rel, items in sorted(corpus.items())}
OUT_DIR.joinpath("corpus.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
total = sum(len(v) for v in out.values())
print(json.dumps({rel: len(v) for rel, v in out.items()}, indent=1))
print("profiles:", len(out), "items:", total)
print("WROTE", OUT_DIR / "corpus.json")
