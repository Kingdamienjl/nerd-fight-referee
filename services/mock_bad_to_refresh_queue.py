from pathlib import Path
from datetime import datetime
import json, re

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "logs" / "mock_duel_quality"
QUEUE = ROOT / "harvest" / "profile_refresh_queue"

def slug_from_path(p):
    return Path(p).stem

def main():
    QUEUE.mkdir(parents=True, exist_ok=True)
    reports = sorted(REPORT_DIR.glob("mock_duel_quality_*.json"))
    if not reports:
        print("no mock reports")
        return

    latest = reports[-1]
    data = json.loads(latest.read_text(errors="ignore"))
    made = 0

    for issue in data.get("issues") or []:
        reasons = []
        reasons += issue.get("bad_patterns") or []
        reasons += issue.get("generic_patterns") or []
        if issue.get("too_short"):
            reasons.append("too_short")
        if issue.get("returncode"):
            reasons.append(f"returncode_{issue.get('returncode')}")

        for key in ["a", "b"]:
            profile_path = issue.get(key)
            if not profile_path:
                continue

            slug = slug_from_path(profile_path)
            out = QUEUE / f"{slug}.json"
            old = {}
            if out.exists():
                try:
                    old = json.loads(out.read_text(errors="ignore"))
                except Exception:
                    old = {}

            data_out = {
                **old,
                "slug": slug,
                "profile_path": profile_path,
                "priority": "p0_mock_duel_failed",
                "reason": "Profile appeared in a mock duel that produced weak/generic/bad fight text.",
                "queued_at": datetime.now().isoformat(timespec="seconds"),
                "latest_mock_output": issue.get("output"),
                "latest_mock_reasons": sorted(set(reasons)),
                "targets": [
                    "remove Profile pending source verification",
                    "remove Basic combat capability fallback",
                    "replace generic profile-backed abilities",
                    "fill signature weapon_power",
                    "fill concrete key_tools",
                    "fill weaknesses/risk",
                    "fill matchup-ready best_route",
                    "rerun mock duel quality gate",
                ],
            }
            out.write_text(json.dumps(data_out, indent=2), encoding="utf-8")
            made += 1

    print(f"latest_report={latest}")
    print(f"mock_failed_profiles_queued={made}")
    print(f"queue={QUEUE}")

if __name__ == "__main__":
    main()
