import json, sys
sys.path.insert(0, "/app"); sys.path.insert(0, "/app/src")
import yaml
from pathlib import Path
targets = ["profiles/needs_review/comics/transformers/rodimus-prime.yaml",
 "profiles/needs_review/comics/transformers/soundwave.yaml",
 "profiles/needs_review/game/castlevania/shanoa.yaml",
 "profiles/needs_review/game/destiny/oryx.yaml",
 "profiles/needs_review/game/elden-ring/maliketh.yaml",
 "profiles/needs_review/game/castlevania/isaac.yaml"]
for rel in targets:
    p = Path("/app/"+rel)
    if not p.exists():
        p = Path("/app/"+rel.replace("needs_review/","generated/",1))
    prof = yaml.safe_load(p.open()) or {}
    ps = prof.get("power_scale") or {}
    srcs = prof.get("sources") or []
    rev = [(str(s.get("source_type")), bool(s.get("revision_id")), bool(s.get("revision_timestamp"))) for s in srcs if isinstance(s, dict)]
    gen = prof.get("generation") or {}
    print(json.dumps({"rel": rel, "exists": str(p), "eligible": prof.get("battle_eligible"),
      "status": prof.get("status"), "ptype": prof.get("profile_type"),
      "conf": gen.get("confidence"), "reasons": gen.get("ineligible_reasons"),
      "AP": bool((ps.get("attack_potency") or {}).get("text") if isinstance(ps.get("attack_potency"), dict) else ps.get("attack_potency")),
      "SP": bool((ps.get("speed") or {}).get("text") if isinstance(ps.get("speed"), dict) else ps.get("speed")),
      "DU": bool((ps.get("durability") or {}).get("text") if isinstance(ps.get("durability"), dict) else ps.get("durability")),
      "n_abilities": len(prof.get("abilities") or []),
      "n_sources": len(srcs), "rev": rev,
      "hash": str(prof.get("profile_hash"))[:12]}))
