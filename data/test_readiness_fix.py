import sys
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.ingest.import_profiles import validate_profile_path, compile_profile
from battlebot.profiles.readiness import assess_readiness
from battlebot.review import service
import yaml

p = Path("/app/profiles/generated/anime/digimon/beelzemon.yaml")
raw = yaml.load(open(p), Loader=yaml.CSafeLoader)
print("readiness on generated file dict: battle_ready =", assess_readiness(raw)["battle_ready"])
model = validate_profile_path(p)
cand = compile_profile(model, p)
print("compiled battle_eligible:", cand.profile["battle_eligible"], "| status:", cand.profile["status"])

# raw needs_review profile (top-level scope) unchanged behavior:
g = yaml.load(open("/app/profiles/needs_review/anime/demon-slayer/genya-shinazugawa.yaml"), Loader=yaml.CSafeLoader)
r = assess_readiness(g)
print("genya (partial scope, stamina piped) blockers include multiple_source_keys:",
      "unresolved_version_scope:multiple_source_keys" in r["blockers"], "| stamina:",
      "unresolved_version_scope:stamina" in r["blockers"])
