#!/usr/bin/env python3
"""Phase 2 audit: demote sweep-stamped battle-eligible profiles.

For every stamped_profiles entry (apply report) flagged battle_eligible:
  - if it has no character_profiles row -> not live, record only;
  - if live and under generated/ -> move the file back to needs_review
    with status/battle_eligible flipped + a continuity_demotion stamp,
    delete the character_profiles row (children cascade), requeue its
    repair job to pending.
Writes /app/data/phase2_demote_report.json with every disposition.
"""
import asyncio
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import asyncpg

from battlebot.profiles import yaml_io
from battlebot.profiles.demotion import apply_demotion_stamp

REPORT = Path("/app/data/continuity_sweep_report.json")
OUT = Path("/app/data/phase2_demote_report.json")
ROOT = Path("/app/profiles")


async def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if report.get("apply") is not True:
        print("REFUSING: report is not an --apply report")
        return 1
    stamped = [s for s in report["stamped_profiles"] if s.get("battle_eligible")]
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    results = []
    for s in stamped:
        rel = s["profile"]
        entry = {"profile": rel, "tainted_source_ids": s["tainted_source_ids"]}
        row = await conn.fetchrow(
            "select profile_id, status from character_profiles where profile_path=$1",
            "profiles/" + rel)
        if row is None:
            entry["disposition"] = "not_live_no_db_row"
            results.append(entry)
            continue
        if not rel.startswith("generated/"):
            entry["disposition"] = "live_but_unexpected_path_skipped"
            entry["db_profile_id"] = row["profile_id"]
            results.append(entry)
            continue
        tail = rel[len("generated/"):]
        src = ROOT / rel
        dst = ROOT / "needs_review" / tail
        profile = yaml_io.load_yaml(src)
        stamp = {
            "rule": "continuity_demotion",
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tainted_source_ids": s["tainted_source_ids"],
            "previous_status": profile.get("status"),
        }
        profile["status"] = "needs_review"
        profile["battle_eligible"] = False
        apply_demotion_stamp(profile, "continuity_demotion", stamp)
        dst.parent.mkdir(parents=True, exist_ok=True)
        yaml_io.write_yaml(dst, profile)
        src.unlink()
        deleted = await conn.execute(
            "delete from character_profiles where profile_id=$1", row["profile_id"])
        job_path = "profiles/needs_review/" + tail
        job = await conn.fetchrow(
            "select id, status from profile_jobs where profile_path=$1", job_path)
        if job:
            await conn.execute(
                "update profile_jobs set status='pending', next_attempt_at=now(), "
                "updated_at=now(), worker_id=null, locked_at=null where id=$1",
                job["id"])
            entry["job"] = f"requeued id={job['id']} from {job['status']}"
        else:
            entry["job"] = "no_job_row"
        entry["db_profile_id"] = row["profile_id"]
        entry["db_delete"] = deleted
        entry["disposition"] = "demoted"
        results.append(entry)
    await conn.close()
    demoted = sum(1 for r in results if r["disposition"] == "demoted")
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "stamped_battle_eligible": len(stamped),
        "demoted": demoted,
        "results": results,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"stamped_battle_eligible": len(stamped), "demoted": demoted,
                      "not_live": len(stamped) - demoted}))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
