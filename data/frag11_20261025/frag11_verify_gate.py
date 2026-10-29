#!/usr/bin/env python3
"""Verify the 2 gate-recovered profiles validate + their eligibility state is consistent."""
import sys
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")
import yaml
from battlebot.review import service
for rel in ("profiles/needs_review/game/god-of-war/gaia.yaml",
            "profiles/needs_review/game/guilty-gear/justice.yaml"):
    p = yaml.load(open("/app/" + rel), Loader=yaml.CSafeLoader)
    print(rel.split("/")[-1],
          "eligible:", p.get("battle_eligible"),
          "status:", p.get("status"),
          "type:", p.get("profile_type"),
          "conf:", (p.get("generation") or {}).get("confidence"),
          "schema_blockers:", service.schema_validation_blockers(p),
          "approval_blockers:", service.approval_blockers(p))
print("VERIFY DONE")
