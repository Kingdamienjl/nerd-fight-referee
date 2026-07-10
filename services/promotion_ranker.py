from pathlib import Path
from datetime import datetime
import json, re

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "harvest" / "promotion_ranked_today.json"
OUT_MD = ROOT / "harvest" / "promotion_top_picks_today.md"

SOURCE_DIRS = [
    ROOT / "harvest" / "promotion_outbox",
    ROOT / "harvest" / "mock_duel_good_outputs",
]

BAD = ["null", "{{", "}}", "profile pending source verification",
       "basic combat capability", "packet-defined fighter",
       "needs source-backed", "undefined"]

GOOD = ["winner", "verdict", "wins", "because", "counter",
        "speed", "durability", "range", "hax", "resistance",
        "win condition", "battle iq", "ability", "tool"]

def title_for(path, text):
    for line in text.splitlines()[:12]:
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()[:120]
    title = re.sub(r"^\d+[_-]+", "", path.stem)
    return title.replace("_", " ").replace("-", " ")[:120]


def score(path):
    text = path.read_text(errors="ignore")
    low = text.lower()
    n = len(text)
    points = 50
    penalties = []
    bonuses = []

    if n < 700:
        points -= 25
        penalties.append("too_short")
    elif n >= 1200:
        points += 10
        bonuses.append("solid_length")

    for bad in BAD:
        if bad in low:
            points -= 30
            penalties.append("bad:" + bad)

    good_hits = sum(1 for g in GOOD if g in low)
    points += min(good_hits * 3, 24)
    if good_hits >= 5:
        bonuses.append("matchup_language")

    if re.search(r"\bvs\.?\b|\bversus\b", low):
        points += 8
        bonuses.append("clear_matchup")

    if re.search(r"\bwin|wins|winner|verdict\b", low):
        points += 8
        bonuses.append("clear_verdict")

    age_hours = (datetime.now().timestamp() - path.stat().st_mtime) / 3600
    if age_hours <= 24:
        points += 8
        bonuses.append("fresh_24h")

    return {
        "score": points,
        "path": str(path.relative_to(ROOT)),
        "title": title_for(path, text),
        "length": n,
        "bonuses": bonuses,
        "penalties": penalties,
        "mtime": path.stat().st_mtime,
    }


def main():
    items = []
    for folder in SOURCE_DIRS:
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
                try:
                    items.append(score(path))
                except Exception as exc:
                    print(f"skip={path} error={exc}")

    best = {}
    for item in items:
        key = re.sub(r"[^a-z0-9]+", "", item["title"].lower())
        if key not in best or item["score"] > best[key]["score"]:
            best[key] = item

    ranked = sorted(best.values(), key=lambda x: (x["score"], x["mtime"]), reverse=True)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(ranked, indent=2))

    lines = [
        "# Promotion Top Picks Today", "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Candidates ranked: {len(ranked)}", "",
    ]

    for i, item in enumerate(ranked[:30], 1):
        lines += [
            f"## {i}. {item['title']}", "",
            f"- Score: {item['score']}",
            f"- File: `{item['path']}`",
            f"- Length: {item['length']}",
            f"- Bonuses: {', '.join(item['bonuses']) or 'none'}",
            f"- Penalties: {', '.join(item['penalties']) or 'none'}",
            "",
        ]

    OUT_MD.write_text("\n".join(lines))

    print(f"ranked={len(ranked)}")
    print(f"json={OUT_JSON}")
    print(f"md={OUT_MD}")
    for item in ranked[:5]:
        print(f"{item['score']:>4} {item['path']}")


if __name__ == "__main__":
    main()
