import sys
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.ingest.import_profiles import validate_profile_path, compile_profile, find_profile_paths
p = Path("/app/profiles/generated/anime/digimon/beelzemon.yaml")
model = validate_profile_path(p)
print("model type:", type(model).__name__)
print("model battle_eligible:", model.battle_eligible, "| status:", model.status, "| profile_type:", model.profile_type)
cand = compile_profile(model, p)
print("candidate battle_eligible:", cand.profile.get("battle_eligible"), "| keys sample:", list(cand.profile)[:8])
print("find_profile_paths includes beelzemon:", any("beelzemon" in str(x) for x in find_profile_paths(Path("/app/profiles/generated"))))
import yaml
raw = yaml.load(open(p), Loader=yaml.CSafeLoader)
print("file battle_eligible:", raw.get("battle_eligible"), "| status:", raw.get("status"), "| profile_type:", raw.get("profile_type"))
