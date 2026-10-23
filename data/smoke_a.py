import sys, glob, json, shutil, asyncio
sys.path.insert(0, "/app/src")
import yaml
from pathlib import Path
from battlebot.review import service, auto_repair

TARGETS = {"missing_ability", "missing_attack_potency", "missing_durability", "missing_speed"}
cands = []
for p in sorted(glob.glob("/app/profiles/needs_review/**/*.yaml", recursive=True)):
    try: prof = yaml.load(open(p), Loader=yaml.CSafeLoader) or {}
    except Exception: continue
    b = set(service.approval_blockers(prof))
    if b & TARGETS:
        srcs = [s for s in prof.get("sources") or [] if isinstance(s, dict) and "wiki" in str(s.get("url") or "")]
        if srcs:
            cands.append((p, sorted(b & TARGETS)))
    if len(cands) >= 3: break
print("candidates:", json.dumps(cands, indent=1))

async def run():
    for src_path, missing in cands:
        tmpdir = Path("/app/data/smoke_a"); tmpdir.mkdir(exist_ok=True)
        work = tmpdir / Path(src_path).name
        shutil.copy(src_path, work)
        notes = tmpdir / "notes.yaml"
        rep = await auto_repair.recover_profile_evidence(work, notes_path=notes, dry_run=False)
        prof = rep.pop("profile", None)
        print("=" * 25, src_path)
        print(" missing targets:", missing)
        print(" recovered:", rep["recovered_fields"], "| parsers:", rep["parser_used"], "| key:", rep["scoped_key"])
        print(" sources tried:", json.dumps(rep["sources_tried"])[:400])
        print(" blockers before:", rep["blockers_before"])
        print(" blockers after: ", rep["blockers_after"])
        print(" identity_mismatch:", rep["identity_mismatch"], "| error:", rep["error"], "| wall:", rep["wall_seconds"])
        if prof:
            ps = prof.get("power_scale") or {}
            for ax in ("attack_potency", "speed", "durability"):
                e = ps.get(ax)
                t = e.get("text") if isinstance(e, dict) else e
                print("  ", ax, "->", str(t)[:100])
            print("   abilities:", len(prof.get("abilities") or []), "| status:", prof.get("status"), "| eligible:", prof.get("battle_eligible"))
asyncio.run(run())
