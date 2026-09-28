"""Rate-limited roster rotation using the harvester's durable cursor."""
import json
import hashlib
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


def generated_snapshot(root=Path("profiles/generated")):
    entries=[]
    for path in sorted(root.rglob("*.yaml")):
        try:
            stat=path.stat()
        except FileNotFoundError:
            continue
        entries.append((str(path),stat.st_size,stat.st_mtime_ns))
    return hashlib.sha256(json.dumps(entries).encode()).hexdigest()


def import_if_changed(state):
    snapshot=generated_snapshot()
    if state.get("last_import_snapshot")==snapshot:
        print(json.dumps({"stage":"import","skipped":"generated_profiles_unchanged"}),flush=True)
        return
    imported=run_bounded([sys.executable,"-P","-m","battlebot.ingest.import_profiles",
                          "profiles/generated","--changed-only"],timeout=300)
    if imported.returncode==0:
        state["last_import_snapshot"]=snapshot
    print(json.dumps({"stage":"import","exit_code":imported.returncode}),flush=True)


def main():
    state_path = Path("data/harvest_rotation.json")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    index = state.get("index", 0)
    while True:
        rosters = sorted(Path("profiles/rosters").glob("*.csv"))
        if not rosters:
            raise RuntimeError("No roster CSV files found")
        roster = rosters[index % len(rosters)]
        cmd = [sys.executable, "-P", "-m", "battlebot.harvest.auto_profile_harvester",
               "--input", str(roster), "--queue-mode", "--max-per-cycle", str(max(1, min(8, int(os.getenv("REFEREE_HARVEST_BATCH", "4"))))), "--quiet-skips"]
        try:
            result = run_bounded(cmd, timeout=600)
            print(json.dumps({"stage": "harvest", "roster": str(roster), "exit_code": result.returncode}), flush=True)
            if result.returncode == 0:
                import_if_changed(state)
        except subprocess.TimeoutExpired:
            print(json.dumps({"stage": "harvest/import", "error": "timeout"}), flush=True)
        index += 1
        temp = state_path.with_suffix(".tmp")
        state["index"] = index
        temp.write_text(json.dumps(state))
        temp.replace(state_path)
        time.sleep(max(60, int(os.getenv("REFEREE_HARVEST_INTERVAL", "180"))))


if __name__ == "__main__":
    main()
