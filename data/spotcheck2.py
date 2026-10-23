import sys
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.review import service

for rel in ["anime/digimon/tentomon.yaml", "anime/dorohedoro/caiman.yaml"]:
    p = Path("/app/profiles/needs_review") / rel
    prof = service.load_yaml(p)
    print("=====", prof.get("name"))
    for axis in ("attack_potency", "speed", "durability"):
        print(f"  {axis}: {str(service.power_text(prof, axis))[:100]}")
    ab = prof.get("abilities") or []
    print("  abilities:", len(ab), "| first:", (str(ab[0].get("name"))[:60] if ab else None))
    print("  blockers:", service.approval_blockers(prof)[:6])
gen = Path("/app/profiles/generated/anime/dorohedoro/shin.yaml")
print("===== Shin generated exists:", gen.exists())
if gen.exists():
    prof = service.load_yaml(gen)
    print("  AP:", str(service.power_text(prof, "attack_potency"))[:90])
    print("  abilities:", len(prof.get("abilities") or []))
