import sys
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.ingest.import_profiles import validate_profile_path, build_import_plan, ImportOptions, load_import_state
p = Path("/app/profiles/generated/anime/digimon/beelzemon.yaml")
try:
    prof = validate_profile_path(p)
    print("validate OK:", prof.get("name"), prof.get("battle_eligible"))
except Exception as e:
    print("validate FAILED:", type(e).__name__)
    print(str(e)[:1200])
state = load_import_state(Path("data/worker_import_state.json"))
compiled, summary = build_import_plan(Path("/app/profiles/generated"), ImportOptions(changed_only=True, import_state=state))
print("plan: scanned", summary.scanned, "changed", summary.changed, "imported", summary.imported,
      "skipped_unchanged", summary.skipped_unchanged, "skipped_invalid", summary.skipped_invalid,
      "skipped_not_eligible", summary.skipped_not_battle_eligible)
for err in summary.errors[:6]:
    print("ERR:", err[:300])
