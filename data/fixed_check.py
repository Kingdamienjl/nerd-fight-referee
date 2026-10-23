import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")
from battlebot.profiles import yaml_io

report = json.loads(Path("/app/data/continuity_sweep_report.json").read_text())
for f in report["fixed"]:
    path = Path("/app/profiles") / f["profile"]
    profile = yaml_io.load_yaml(path)
    entries = [e for e in profile.get("sources") or []
               if isinstance(e, dict) and e.get("id") == f["source_id"]]
    for e in entries:
        print(f["profile"], "|", f["source_id"], "| title now:", e.get("title"),
              "| repair_stamp:", "continuity_repair" in e,
              "| suspect:", bool(e.get("continuity_suspect")),
              "| rev:", e.get("revision_id"))
    if not entries:
        print(f["profile"], "|", f["source_id"], "| ENTRY GONE")
