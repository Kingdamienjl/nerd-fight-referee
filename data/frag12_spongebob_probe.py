"""SpongeBob source diagnosis (read-only): dump the profile's recorded
sources and blockers, and check what the recovery path would fetch."""
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import service

rel = "profiles/needs_review/mixed/adult-cartoons/spongebob-squarepants.yaml"
prof = yaml.load(open("/app/" + rel), Loader=yaml.CSafeLoader) or {}
print("blockers:", service.approval_blockers(prof))
for s in prof.get("sources") or []:
    print(repr(s.get("id")), "|", repr(s.get("parser")), "|",
          repr(s.get("url")), "|", repr(s.get("title")),
          "| rev:", bool(s.get("revision_id")))
print("power_scale keys:", list((prof.get("power_scale") or {}).keys()))
print("abilities:", len(prof.get("abilities") or []),
      "weaknesses:", len(prof.get("weaknesses") or []))
