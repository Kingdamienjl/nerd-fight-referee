from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = ROOT / "logs" / "evening_duplicate_audit_last_run.txt"
REPORT = ROOT / "logs" / "evening_duplicate_audit_report.json"

SCRIPTS = [
    "src/battlebot/review/duplicate_audit.py",
    "src/battlebot/review/fight_output_audit.py",
    "services/proactive_post_preflight.py",
]

def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def hour() -> int:
    return datetime.now().hour

def run_command(script: str) -> dict:
    path = ROOT / script
    if not path.exists():
        return {"script": script, "status": "missing"}

    cmd = ["python", script]
    if script.endswith("fight_output_audit.py"):
        cmd = ["python", "-m", "battlebot.review.fight_output_audit"]

    proc = subprocess.run(
        cmd,
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

    if hour() < 18:
        print("evening_duplicate_audit=not_evening_yet")
        return

    if STAMP.exists() and STAMP.read_text().strip() == today():
        print("evening_duplicate_audit=already_ran_today")
        return

    results = [run_command(script) for script in SCRIPTS]

    STAMP.write_text(today())
    REPORT.write_text(json.dumps({
        "time": datetime.now().isoformat(timespec="seconds"),
        "date": today(),
        "results": results,
    }, indent=2))

    print("evening_duplicate_audit=ran")
    print(f"report={REPORT}")

if __name__ == "__main__":
    main()
