import sys, json
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.review import service

prog = json.loads(Path("/app/data/recovery_progress.json").read_text())
print("progress entries:", len(prog), "| sample values:", list(prog.items())[:2])
results = Path("/app/data/recovery_results.json")
res = json.loads(results.read_text()) if results.exists() else {}
rows = res.get("profiles") or res.get("results") or []
print("results rows:", len(rows), "| summary keys:", [k for k in res if k not in ("profiles","results")])
rec = [r for r in rows if r.get("recovered_fields")]
print("rows with recoveries:", len(rec))
JUNK = ("a-z-animals", "Specimens grow", "animalia", "species of", "genus ")
for r in rec:
    p = Path("/app") / r["path"]
    if not p.exists(): continue
    prof = service.load_yaml(p)
    texts = " ".join(str(service.power_text(prof, a) or "") for a in ("attack_potency","speed","durability"))
    flag = "  <<< JUNK?" if any(j in texts for j in JUNK) else ""
    print(f"- {prof.get('name')}: AP={str(service.power_text(prof,'attack_potency'))[:70]!r}{flag}")
