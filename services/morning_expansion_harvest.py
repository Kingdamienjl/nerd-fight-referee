from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = ROOT / "logs" / "morning_expansion_harvest_last_run.txt"
REPORT = ROOT / "logs" / "morning_expansion_harvest_report.json"

SCRIPTS = [
    "services/seed_expansion_needs_review.py",
    "services/outbox_to_needs_review.py",
    "services/queue_missing_fighter.py",
    "services/harvest_to_promotion_outbox.py",
    "services/queue_weak_generated_profiles.py",
]

def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def run_script(script: str) -> dict:
    path = ROOT / script
    if not path.exists():
        return {"script": script, "status": "missing"}

    proc = subprocess.run(
        ["python", script],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=900,
    )
    return {
        "script": script,
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "output_tail": proc.stdout[-4000:],
    }

def main() -> None:
    STAMP.parent.mkdir(parents=True, exist_ok=True)

    if STAMP.exists() and STAMP.read_text().strip() == today():
        print("morning_expansion_harvest=already_ran_today")
        return

    results = [run_script(script) for script in SCRIPTS]

    STAMP.write_text(today())
    REPORT.write_text(json.dumps({
        "time": datetime.now().isoformat(timespec="seconds"),
        "date": today(),
        "results": results,
    }, indent=2))

    print("morning_expansion_harvest=ran")
    print(f"report={REPORT}")

if __name__ == "__main__":
    main()
