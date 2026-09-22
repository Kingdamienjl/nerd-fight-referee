"""Rate-limited roster rotation using the harvester's durable cursor."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile


def run_bounded(command, timeout):
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(command, timeout=timeout, check=False, stdout=output, stderr=output)
        size = output.tell()
        output.seek(max(0, size - 8000))
        tail = output.read().decode("utf-8", errors="replace")
        print(json.dumps({"stage": "subprocess", "exit_code": result.returncode, "output_bytes": size, "output_tail": tail}), flush=True)
        return result


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
               "--input", str(roster), "--queue-mode", "--max-per-cycle", str(max(1, min(8, int(os.getenv("REFEREE_HARVEST_BATCH", "4"))))), "--quiet-skips"]
        try:
            result = run_bounded(cmd, timeout=600)
            print(json.dumps({"stage": "harvest", "roster": str(roster), "exit_code": result.returncode}), flush=True)
            if result.returncode == 0:
                imported = run_bounded([sys.executable, "-m", "battlebot.ingest.import_profiles",
                    "profiles/generated", "--changed-only"], timeout=300)
                print(json.dumps({"stage": "import", "exit_code": imported.returncode}), flush=True)
        except subprocess.TimeoutExpired:
            print(json.dumps({"stage": "harvest/import", "error": "timeout"}), flush=True)
        index += 1
        temp = state_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"index": index}))
        temp.replace(state_path)
        time.sleep(max(60, int(os.getenv("REFEREE_HARVEST_INTERVAL", "180"))))


if __name__ == "__main__":
    main()
