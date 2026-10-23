#!/usr/bin/env python3
"""Frag-3 Part-1 demotion follow-through (mirrors phase2_demote).

The template cleanup removed the only 'content' propping up 6
profiles' battle eligibility: post-cleanup they no longer compile
as battle_eligible, so the eligibility-gated importer freezes their
character_profiles rows WITH the debris still in them. Disposition
(same as the continuity demotions): restore rimuru's schema-
required attack_potency entry to the canonical empty form, move
each file generated/ -> needs_review/ with status flipped + a
template_cleanup_demotion stamp, delete the character_profiles row
(children cascade), requeue an existing needs_review job row.
Aborts per-profile if the needs_review destination already exists.
"""
import asyncio
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.common.db import connect_database
from battlebot.profiles import yaml_io

ROOT = Path("/app/profiles")
SCHEMA_ORDER = (
    "tier", "attack_potency", "speed", "lifting_strength",
    "striking_strength", "durability", "stamina", "range",
    "intelligence",
)
TAILS = (
    "anime/dragon-ball/beerus-game.yaml",
    "anime/dragon-ball/cell-classic.yaml",
    "anime/dragon-ball/future-trunks-anime.yaml",
    "anime/dragon-ball/trunks-anime.yaml",
    "anime/dragon-ball/vegeta-classic.yaml",
    "anime/that-time-i-got-reincarnated-as-a-slime/rimuru-tempest.yaml",
)
RIMURU = "anime/that-time-i-got-reincarnated-as-a-slime/rimuru-tempest.yaml"


async def main() -> int:
    results = []
    async with connect_database() as conn:
        for tail in TAILS:
            entry = {"profile": "profiles/generated/" + tail}
            src = ROOT / "generated" / tail
            dst = ROOT / "needs_review" / tail
            if not src.exists():
                entry["disposition"] = "src_missing"
                results.append(entry)
                continue
            if dst.exists():
                entry["disposition"] = "ABORT_dst_exists"
                results.append(entry)
                continue
            profile = yaml_io.load_yaml(src)
            if tail == RIMURU:
                ps = profile.get("power_scale") or {}
                if "attack_potency" not in ps:
                    rebuilt = {}
                    for key in SCHEMA_ORDER:
                        if key == "attack_potency":
                            rebuilt[key] = {
                                "text": "",
                                "source_ids": [],
                                "confidence": 0.0,
                            }
                        elif key in ps:
                            rebuilt[key] = ps[key]
                    for key, value in ps.items():
                        rebuilt.setdefault(key, value)
                    profile["power_scale"] = rebuilt
                    entry["rimuru_ap_entry_restored"] = True
            row = await conn.fetchrow(
                "select profile_id, status from character_profiles "
                "where profile_path=$1",
                "profiles/generated/" + tail,
            )
            stamp = {
                "rule": "template_cleanup_demotion",
                "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "reason": (
                    "post-cleanup profile no longer compiles "
                    "battle_eligible; importer froze its DB row with "
                    "CSPW template debris in it"
                ),
                "previous_status": profile.get("status"),
            }
            profile["status"] = "needs_review"
            profile["battle_eligible"] = False
            profile["template_cleanup_demotion"] = stamp
            dst.parent.mkdir(parents=True, exist_ok=True)
            yaml_io.write_yaml(dst, profile)
            src.unlink()
            if row is not None:
                deleted = await conn.execute(
                    "delete from character_profiles where profile_id=$1",
                    row["profile_id"],
                )
                entry["db_delete"] = deleted
            else:
                entry["db_delete"] = "no_row"
            job = await conn.fetchrow(
                "select id, status from profile_jobs where profile_path=$1",
                "profiles/needs_review/" + tail,
            )
            if job:
                await conn.execute(
                    "update profile_jobs set status='pending', "
                    "next_attempt_at=now(), updated_at=now(), "
                    "worker_id=null, locked_at=null where id=$1",
                    job["id"],
                )
                entry["job"] = f"requeued id={job['id']} from {job['status']}"
            else:
                entry["job"] = "no_job_row"
            entry["disposition"] = "demoted"
            results.append(entry)
        total = await conn.fetchval("SELECT count(*) FROM character_profiles")
        print("battle_eligible_after_demote:", total)
    for entry in results:
        print(json.dumps(entry, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
