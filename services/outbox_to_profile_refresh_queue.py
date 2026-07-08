from pathlib import Path
from datetime import datetime
import re, json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "harvest" / "promotion_outbox"
GEN = ROOT / "profiles" / "generated"
QUEUE = ROOT / "harvest" / "profile_refresh_queue"

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
            a,b = line.split(" VS ",1)
            return clean(a), clean(b)
    return None

GEN_INDEX = {}
for p in list(GEN.rglob("*.yaml")) + list(GEN.rglob("*.yml")):
    GEN_INDEX.setdefault(p.stem, p.as_posix())

def main():
    QUEUE.mkdir(parents=True, exist_ok=True)
    made = skipped = missing = 0
    seen = set()

    for path in sorted(OUT.glob("*.md")):
        pair = parse_title(path.read_text(errors="ignore"))
        if not pair:
            skipped += 1
            continue

        a,b = pair
        for name, opp in [(a,b),(b,a)]:
            slug = slugify(name)
            if slug in seen:
                continue
            seen.add(slug)

            profile_path = GEN_INDEX.get(slug)
            if not profile_path:
                missing += 1
                continue

            out = QUEUE / f"{slug}.json"
            data = {
                "name": name,
                "slug": slug,
                "profile_path": profile_path,
                "priority": "p0_hot_outbox_refresh",
                "reason": "Generated profile appears in promotion_outbox and should be checked/enriched for better battle cards.",
                "opponent_context": opp,
                "source_file": path.as_posix(),
                "queued_at": datetime.now().isoformat(timespec="seconds"),
                "targets": [
                    "verify franchise/category",
                    "fill combat style",
                    "fill weapon_power",
                    "fill key_tools",
                    "fill weaknesses",
                    "fill best_route",
                    "improve battle-card wording",
                ],
            }
            out.write_text(json.dumps(data, indent=2), encoding="utf-8")
            made += 1

    print(f"refresh_queue_created={made}")
    print(f"missing_not_generated={missing}")
    print(f"skipped_files={skipped}")
    print(f"queue={QUEUE}")

if __name__ == "__main__":
    main()
