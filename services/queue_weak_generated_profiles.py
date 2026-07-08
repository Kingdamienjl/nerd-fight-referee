from pathlib import Path
from datetime import datetime
import json, yaml

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "profiles" / "generated"
QUEUE = ROOT / "harvest" / "profile_refresh_queue"

def load(p):
    try:
        return yaml.safe_load(p.read_text(errors="ignore")) or {}
    except Exception:
        return {}

def main():
    QUEUE.mkdir(parents=True, exist_ok=True)
    made = 0
    for p in sorted(GEN.rglob("*.yaml")):
        raw = p.read_text(errors="ignore")
        if "profile pending source verification" not in raw.lower():
            continue
        data = load(p)
        name = data.get("name") or p.stem
        out = QUEUE / f"{p.stem}.json"
        out.write_text(json.dumps({
            "name": name,
            "slug": p.stem,
            "profile_path": p.as_posix(),
            "priority": "p0_pending_source_verification",
            "reason": "Generated profile still contains placeholder/pending-source text and is not battle-certified.",
            "queued_at": datetime.now().isoformat(timespec="seconds"),
            "targets": [
                "replace Profile pending source verification",
                "fill signature weapon_power",
                "fill key_tools",
                "fill weaknesses/risk",
                "fill concrete best_route",
                "rerun mock duel quality gate",
            ],
        }, indent=2), encoding="utf-8")
        made += 1
    print(f"weak_profiles_queued={made}")
    print(f"queue={QUEUE}")

if __name__ == "__main__":
    main()
