import sys, json
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.review import service

prog = json.loads(Path("/app/data/recovery_progress.json").read_text())
rec = {k: v for k, v in prog.items() if v.get("recovered_fields")}
print(f"processed={len(prog)} recovered_any={len(rec)} promoted={sum(1 for v in prog.values() if v.get('promoted'))}")
print(f"identity mismatches flagged: {sum(1 for v in prog.values() if v.get('identity_mismatch'))}")
JUNK = ("a-z-animals", "Specimens grow", "animalia", "species of", "genus ", "wikipedia.org/wiki/Caiman")
for rel, r in sorted(rec.items()):
    p = Path("/app") / rel
    prof = service.load_yaml(p)
    texts = " ".join(str(service.power_text(prof, a) or "") for a in ("attack_potency","speed","durability"))
    flag = "  <<< JUNK?" if any(j in texts for j in JUNK) else ""
    print(f"- {prof.get('name')}: {r['recovered_fields']} AP={str(service.power_text(prof,'attack_potency'))[:64]!r}{flag}")
