from __future__ import annotations
import argparse, re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "profiles" / "generated"
NR = ROOT / "profiles" / "needs_review" / "mixed" / "user-requests"

FRANCHISE_HINTS = {
    "naruto":"anime","boruto":"anime","dragon ball":"anime","dbz":"anime","bleach":"anime",
    "one piece":"anime","chainsaw man":"anime","jujutsu kaisen":"anime","demon slayer":"anime",
    "my hero academia":"anime","jojo":"anime","hellsing":"anime","berserk":"anime",
    "marvel":"comics","dc":"comics","earth-616":"comics","batman":"comics","superman":"comics",
    "spider-man":"comics","x-men":"comics",
    "final fantasy":"game","kingdom hearts":"game","devil may cry":"game","pokemon":"game",
    "zelda":"game","mario":"game","sonic":"game","mortal kombat":"game","street fighter":"game",
    "star wars":"movie_tv","lord of the rings":"movie_tv","harry potter":"movie_tv",
    "avatar":"cartoon","steven universe":"cartoon","adventure time":"cartoon",
}

def slugify(x: str) -> str:
    x = re.sub(r"\([^)]*\)", "", x.lower())
    x = re.sub(r"[^a-z0-9]+", "-", x)
    return x.strip("-") or "unknown-fighter"

def infer_franchise(name: str) -> str:
    m = re.search(r"\(([^)]+)\)", name)
    if m:
        return m.group(1).strip()
    low = name.lower()
    for key in FRANCHISE_HINTS:
        if key in low:
            return key.title()
    return "unknown"

def infer_category(name: str, franchise: str) -> str:
    low = (name + " " + franchise).lower()
    for key, cat in FRANCHISE_HINTS.items():
        if key in low:
            return cat
    return "mixed"

def exists_anywhere(slug: str) -> bool:
    hits = list(GEN.rglob(f"{slug}.yaml")) + list(GEN.rglob(f"{slug}.yml"))
    hits += list(NR.rglob(f"{slug}.yaml")) + list(NR.rglob(f"{slug}.yml"))
    return bool(hits)

def read_count(path: Path) -> int:
    if not path.exists():
        return 0
    m = re.search(r"request_count:\s*(\d+)", path.read_text(errors="ignore"))
    return int(m.group(1)) if m else 1

def priority(source: str, count: int, category: str, franchise: str) -> str:
    if source == "fight_command":
        return "p0_hot"
    if count >= 3:
        return "p1_repeat"
    if franchise != "unknown":
        return "p2_known_franchise"
    if category != "mixed":
        return "p2_known_category"
    return "p3_normal"

def yaml_list(items):
    return "\n".join(f'  - "{str(i).replace(chr(34), chr(39))}"' for i in items)

def queue(name: str, source: str, opponent: str | None, requested_by: str | None):
    name = name.strip()
    slug = slugify(name)
    franchise = infer_franchise(name)
    category = infer_category(name, franchise)
    outdir = NR / category / slug[:1]
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{slug}.yaml"

    if exists_anywhere(slug) and not out.exists():
        print(f"already exists elsewhere: {name}")
        return

    count = read_count(out) + 1
    pri = priority(source, count, category, franchise)
    now = datetime.now().isoformat(timespec="seconds")

    targets = [
        f"Search exact character name: {name}",
        f"Search franchise + character: {franchise} {name}" if franchise != "unknown" else f"Identify franchise for {name}",
        "Check VS Battles / SuperheroDB / ComicVine / Fandom-style sources where applicable",
    ]
    if opponent:
        targets.append(f"Requested matchup context: {name} vs {opponent}")

    text = f'''name: "{name}"
id: "{slug}"
slug: "{slug}"
category: "{category}"
franchise: "{franchise}"
source_status: "needs_review"
profile_status: "missing_contender_placeholder"

queue:
  priority: "{pri}"
  request_count: {count}
  first_seen_source: "{source}"
  last_requested_at: "{now}"
  requested_by: "{requested_by or 'unknown'}"
  opponent_context: "{opponent or ''}"
  reason: "Requested as a missing fight contender."

research:
  category_guess: "{category}"
  franchise_guess: "{franchise}"
  source_candidates:
{yaml_list(["vsbattles", "superherodb", "comicvine", "fandom", "manual_web_search"])}
  research_targets:
{yaml_list(targets)}

combat_identity:
  identity_summary: "{name} was requested as a contender, but no clean local profile was found yet."
  combat_style: "profile pending source verification"

weapon_power:
  - "Profile pending source verification"
key_tools:
  - "Profile pending source verification"
strengths:
  - "Requested by user matchup input"
weaknesses:
  - "Source verification pending"
best_route: "Needs source-backed profile data before a confident win route can be assigned."
risk: "Source verification pending"
notes:
  - "Auto-queued from missing contender name."
'''
    out.write_text(text, encoding="utf-8")
    print(f"queued {pri}: {out}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--source", default="manual")
    ap.add_argument("--opponent", default="")
    ap.add_argument("--requested-by", default="")
    args = ap.parse_args()
    for n in args.names:
        queue(n, args.source, args.opponent, args.requested_by)

if __name__ == "__main__":
    main()
