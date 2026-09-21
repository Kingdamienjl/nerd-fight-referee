"""Rate-limited roster rotation using the harvester's durable cursor."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    state_path = Path("data/harvest_rotation.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    index = json.loads(state_path.read_text()).get("index", 0) if state_path.exists() else 0
    while True:
        rosters = sorted(Path("profiles/rosters").glob("*.csv"))
        if not rosters:
            raise RuntimeError("No roster CSV files found")
        roster = rosters[index % len(rosters)]
        cmd = [sys.executable, "-m", "battlebot.harvest.auto_profile_harvester",
               "--input", str(roster), "--queue-mode", "--max-per-cycle", "3", "--quiet-skips"]
        try:
            result = subprocess.run(cmd, timeout=600, check=False)
            print(json.dumps({"stage": "harvest", "roster": str(roster), "exit_code": result.returncode}), flush=True)
            if result.returncode == 0:
                imported = subprocess.run([sys.executable, "-m", "battlebot.ingest.import_profiles",
                    "profiles/generated", "--changed-only"], timeout=300, check=False)
                print(json.dumps({"stage": "import", "exit_code": imported.returncode}), flush=True)
        except subprocess.TimeoutExpired:
            print(json.dumps({"stage": "harvest/import", "error": "timeout"}), flush=True)
        index += 1
        temp = state_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"index": index}))
        temp.replace(state_path)
        time.sleep(max(60, int(os.getenv("REFEREE_HARVEST_INTERVAL", "300"))))


if __name__ == "__main__":
    main()
