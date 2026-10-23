import sys, json
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.review import service
prog = json.loads(Path("/app/data/recovery_progress.json").read_text())
for rel in ["anime/dorohedoro/caiman.yaml", "anime/chainsaw-man/yoru.yaml",
            "anime/digimon/tai-kamiya.yaml", "anime/claymore/galatea.yaml"]:
    key = f"profiles/needs_review/{rel}"
    prof = service.load_yaml(Path("/app") / key)
    now = service.approval_blockers(prof)
    print(prof.get("name"), "| blockers now:", now, "| matches pre-run:", now == prog[key]["blockers_before"])
