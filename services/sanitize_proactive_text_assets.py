from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = [
    ROOT / "harvest" / "promotion_outbox",
    ROOT / "harvest" / "promo_candidates",
    ROOT / "harvest" / "social_posts_tonight.md",
    ROOT / "harvest" / "promotion_pack_tonight.md",
]

REPLACEMENTS = {
    "The AI Nerd Referee has spoken. Drop the next matchup.": "The ref has ruled. Drop the next matchup.",
    "AI Nerd Referee has spoken. Drop the next matchup.": "The ref has ruled. Drop the next matchup.",
    "The bracket goblin in the striped shirt has a call:": "The ref checks the tape and makes the call:",
    "Power-scaling chalkboard is out, and the call is:": "Power-scaling board is up, and the call is:",
    "The nerd tribunal is in session:": "The ref opens the case file:",
    "This is the kind of matchup that starts arguments at 2 AM, and the ref is ready:": "This one has debate-room energy, and the ref is ready:",
    "wins the ugly middle of the fight, and that is where this matchup breaks.": "wins the key exchange, and that is where this matchup breaks.",
    "has the cleaner fight script, safer answers, and the more believable finish.": "has the cleaner route, safer answers, and the more believable finish.",
    "needed the cleaner exploit, and the files do not give them enough of it.": "needed a cleaner exploit than the matchup evidence supports.",
    "has upset energy, just not enough reliable control of the fight.": "has upset potential, but not enough reliable control of the exchange.",
}

def iter_files(target):
    if target.is_file():
        yield target
    elif target.is_dir():
        yield from target.rglob("*.md")
        yield from target.rglob("*.txt")

def main():
    changed = 0
    scanned = 0

    for target in TARGETS:
        if not target.exists():
            continue
        for p in iter_files(target):
            scanned += 1
            try:
                s = p.read_text(errors="ignore")
            except Exception:
                continue

            old = s
            for a, b in REPLACEMENTS.items():
                s = s.replace(a, b)

            if s != old:
                p.write_text(s, encoding="utf-8")
                changed += 1

    print(f"scanned={scanned}")
    print(f"changed={changed}")

if __name__ == "__main__":
    main()
