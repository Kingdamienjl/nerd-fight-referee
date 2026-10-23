import sys, shutil
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.review import service

root = Path("/app/data/sanitize_test")
if root.exists(): shutil.rmtree(root)
nr = root / "needs_review"; gen = root / "generated"
rel = Path("anime/digimon/beelzemon.yaml")
(nr / rel.parent).mkdir(parents=True)
shutil.copy(f"/app/profiles/needs_review/{rel}", nr / rel)
notes = root / "notes.yaml"
res = service.approve_profile(nr / rel, needs_review_dir=nr, generated_dir=gen, notes_path=notes, approved_by="auto_repair")
print("approve ok:", res.get("ok"), "| error:", res.get("error"))
dest = Path(res["destination"])
prof = service.load_yaml(dest)
print("generated exists:", dest.exists())
print("top-level version_scope present:", "version_scope" in prof)
print("review.version_scope:", (prof.get("review") or {}).get("version_scope"))
print("schema blockers on generated:", service.schema_validation_blockers(prof))
