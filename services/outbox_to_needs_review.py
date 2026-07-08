from pathlib import Path
from datetime import datetime
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "harvest" / "promotion_outbox"
GEN = ROOT / "profiles" / "generated"
NR = ROOT / "profiles" / "needs_review" / "mixed" / "user-requests"

HINTS = {
    "bleach":"anime","chainsaw":"anime","demon slayer":"anime","dragon ball":"anime",
    "jojo":"anime","berserk":"anime","one piece":"anime","sailor moon":"anime",
    "evangelion":"anime","code geass":"anime","hunter":"anime","my hero":"anime",
    "black clover":"anime","yu yu":"anime","gurren":"anime","trigun":"anime",
    "final fantasy":"game","zelda":"game","pokemon":"game","league":"game",
    "street fighter":"game","mortal kombat":"game","sekiro":"game",
    "dark souls":"game","bloodborne":"game",
    "marvel":"comics","dc":"comics","earth-616":"comics","invincible":"comics",
}

def slugify(x):
    x = re.sub(r"\([^)]*\)", "", x.lower())
    x = re.sub(r"[^a-z0-9]+", "-", x)
    return x.strip("-") or "unknown"

def clean(x):
    return x.strip().strip("#").strip("*").strip()

def parse_title(text):
    for line in text.splitlines():
        line = clean(line)
        if " VS " in line:
            a, b = line.split(" VS ", 1)
            return clean(a), clean(b)
    return None

def franchise(name):
    m = re.search(r"\(([^)]+)\)", name)
    return m.group(1).strip() if m else "unknown"

def category(name, fran):
    low = (name + " " + fran).lower()
    for k, v in HINTS.items():
        if k in low:
            return v
    return "mixed"

GEN_INDEX = {p.stem for p in GEN.rglob("*.yaml")} | {p.stem for p in GEN.rglob("*.yml")}
REVIEW_ROOT = ROOT / "profiles" / "needs_review"
REVIEW_INDEX = {p.stem for p in REVIEW_ROOT.rglob("*.yaml")} | {p.stem for p in REVIEW_ROOT.rglob("*.yml")}

def exists_generated(slug):
    return slug in GEN_INDEX

def exists_review(slug):
    return slug in REVIEW_INDEX

def q(x):
    return str(x).replace('"', "'")

def write_profile(name, opp, src):
    slug = slugify(name)
    if exists_generated(slug):
        return "skip_generated"
    if exists_review(slug):
        return "skip_review"

    fran = franchise(name)
    cat = category(name, fran)
    outdir = NR / cat / slug[:1]
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{slug}.yaml"
    now = datetime.now().isoformat(timespec="seconds")

    out.write_text(f'''name: "{q(name)}"
id: "{slug}"
slug: "{slug}"
category: "{cat}"
franchise: "{q(fran)}"
source_status: "needs_review"
profile_status: "review_profile_from_promotion_outbox"

queue:
  priority: "p0_hot"
  request_count: 1
  first_seen_source: "promotion_outbox"
  last_requested_at: "{now}"
  requested_by: "harvest_outbox"
  opponent_context: "{q(opp)}"
  source_file: "{q(src)}"
  reason: "Appeared in harvested promotion outbox and needs source-backed enrichment."

research:
  category_guess: "{cat}"
  franchise_guess: "{q(fran)}"
  source_candidates:
    - "vsbattles"
    - "superherodb"
    - "comicvine"
    - "fandom"
    - "manual_web_search"
  research_targets:
    - "Find exact character profile for {q(name)}"
    - "Confirm franchise/canon/source for {q(name)}"
    - "Collect powers, weapons, weaknesses, and combat style"
    - "Use matchup context: {q(name)} vs {q(opp)}"

combat_identity:
  identity_summary: "{q(name)} appeared in a harvested fight result and needs source-backed enrichment."
  combat_style: "profile pending source verification"
weapon_power:
  - "Profile pending source verification"
key_tools:
  - "Profile pending source verification"
strengths:
  - "Appeared in harvested matchup candidate"
weaknesses:
  - "Source verification pending"
best_route: "Needs source-backed profile data before a confident win route can be assigned."
risk: "Source verification pending"
notes:
  - "Created from promotion outbox."
''', encoding="utf-8")
    return "created"

def main():
    created = sg = sr = bad = 0
    for path in sorted(OUT.glob("*.md")):
        pair = parse_title(path.read_text(errors="ignore"))
        if not pair:
            bad += 1
            continue
        a, b = pair
        for name, opp in [(a,b), (b,a)]:
            r = write_profile(name, opp, path.as_posix())
            if r == "created": created += 1
            elif r == "skip_generated": sg += 1
            elif r == "skip_review": sr += 1
    print(f"created={created}")
    print(f"skip_generated={sg}")
    print(f"skip_review_exists={sr}")
    print(f"skipped_files={bad}")

if __name__ == "__main__":
    main()
