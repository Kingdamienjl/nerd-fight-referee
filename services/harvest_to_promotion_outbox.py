from __future__ import annotations
import re, shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAND = ROOT / "harvest" / "promo_candidates"
OUT = ROOT / "harvest" / "promotion_outbox"
ARCHIVE = ROOT / "harvest" / "promotion_outbox_archive"
REQ = ROOT / "profiles" / "needs_review" / "mixed" / "user-requests"

def slugify(x: str) -> str:
    x = re.sub(r"\([^)]*\)", "", x.lower())
    x = re.sub(r"[^a-z0-9]+", "-", x)
    return x.strip("-") or "unknown"

def existing_profile(slug: str) -> bool:
    for root in [ROOT / "profiles" / "generated", ROOT / "profiles" / "needs_review"]:
        if list(root.rglob(f"{slug}.yaml")) or list(root.rglob(f"{slug}.yml")):
            return True
    return False

def infer_category(name: str) -> str:
    low = name.lower()
    anime = ["naruto","bleach","one piece","chainsaw","jujutsu","demon slayer","dragon ball","jojo","hellsing","berserk"]
    game = ["final fantasy","zelda","pokemon","sonic","mario","street fighter","mortal kombat","kingdom hearts"]
    comics = ["marvel","dc","earth-616","batman","superman","spider-man","x-men"]
    if any(x in low for x in anime): return "anime"
    if any(x in low for x in game): return "game"
    if any(x in low for x in comics): return "comics"
    return "mixed"

def queue_request(name: str, opponent: str) -> None:
    slug = slugify(name)
    if existing_profile(slug):
        return
    cat = infer_category(name)
    d = REQ / cat / slug[:1]
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{slug}.yaml"
    count = 1
    if p.exists():
        m = re.search(r"request_count:\s*(\d+)", p.read_text(errors="ignore"))
        count = int(m.group(1)) + 1 if m else 2
    priority = "p1_repeat" if count >= 3 else "p0_hot"
    now = datetime.now().isoformat(timespec="seconds")
    p.write_text(f'''name: "{name}"
id: "{slug}"
slug: "{slug}"
category: "{cat}"
franchise: "unknown"
source_status: "needs_review"
profile_status: "missing_contender_from_harvest"

queue:
  priority: "{priority}"
  request_count: {count}
  first_seen_source: "harvest_promo_candidates"
  last_requested_at: "{now}"
  requested_by: "harvest_bridge"
  opponent_context: "{opponent}"
  reason: "Appeared in harvested promo candidate list."

research:
  category_guess: "{cat}"
  franchise_guess: "unknown"
  source_candidates:
    - "vsbattles"
    - "superherodb"
    - "comicvine"
    - "fandom"
    - "manual_web_search"
  research_targets:
    - "Find exact character profile for {name}"
    - "Use matchup context: {name} vs {opponent}"

combat_identity:
  identity_summary: "{name} appeared in a harvested fight candidate but needs source verification."
  combat_style: "profile pending source verification"
weapon_power:
  - "Profile pending source verification"
key_tools:
  - "Profile pending source verification"
strengths:
  - "Appeared in harvested matchup candidate"
weaknesses:
  - "Source verification pending"
best_route: "Needs source-backed profile data before a confident route can be assigned."
risk: "Source verification pending"
notes:
  - "Auto-queued from harvest promotion bridge."
''', encoding="utf-8")

def parse_title(text: str) -> tuple[str, str] | None:
    for line in text.splitlines():
        line = line.strip("# *")
        if " VS " in line:
            a, b = line.split(" VS ", 1)
            return a.strip(), b.strip()
    return None

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    made = queued = skipped = 0

    for src in sorted(CAND.glob("*.md")):
        text = src.read_text(errors="ignore")
        parsed = parse_title(text)
        if not parsed:
            skipped += 1
            continue

        a, b = parsed
        dst = OUT / src.name
        if not dst.exists():
            header = f"<!-- promoted_from: {src} at {datetime.now().isoformat(timespec='seconds')} -->\n\n"
            dst.write_text(header + text, encoding="utf-8")
            made += 1

        queue_request(a, b)
        queue_request(b, a)
        queued += 2

    print(f"promotion_outbox_added={made} missing_request_checks={queued} skipped={skipped}")
    print(f"outbox={OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
