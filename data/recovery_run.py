"""Fix A: evidence-recovery batch over needs_review profiles.

Cohort: profiles blocked on missing_ability / missing_clean_linked_ability /
missing_attack_potency / missing_durability / missing_speed / unlinked_stat:*.
For each, auto_repair.recover_profile_evidence re-extracts ONLY the missing
evidence from the profile's OWN recorded sources via the harvest fallback
parser chain (+ LLM step when HARVEST_LLM_FALLBACK=1), merges without
overwriting usable evidence, and this runner promotes through the real
approval gate when the profile comes fully clean.

Queue safety: cohort jobs are held by pushing next_attempt_at +2 days
(claim requires next_attempt_at <= now()); held jobs are released at the
end of the run -- processed ones with refreshed blocker-count priority,
promoted ones marked 'promoted', untouched ones simply un-held. Progress
is persisted after every profile (data/recovery_progress.json) so a
restart never redoes finished profiles.

LLM wedge watch: if the rolling median wall time of LLM-involved profiles
exceeds the threshold, HARVEST_LLM_FALLBACK is switched off mid-run and
the batch continues parser-only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

import yaml

from battlebot.common.db import connect_database, database_url
from battlebot.review import auto_repair, queue, queue_worker, service

TARGET_BLOCKERS = {
    "missing_ability",
    "missing_clean_linked_ability",
    "missing_attack_potency",
    "missing_durability",
    "missing_speed",
    "unlinked_stat:attack_potency",
    "unlinked_stat:durability",
    "unlinked_stat:speed",
}
COHORT_PATH = Path("data/recovery_cohort.json")
PROGRESS_PATH = Path("data/recovery_progress.json")
RESULTS_PATH = Path("data/recovery_results.json")
WEDGE_MEDIAN_SECONDS = 180.0


def build_cohort() -> dict[str, list[str]]:
    cohort: dict[str, list[str]] = {}
    needs_dir = service.DEFAULT_NEEDS_REVIEW_DIR
    for path in sorted(needs_dir.rglob("*.yaml")):
        try:
            with open(path) as handle:
                profile = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
        except Exception:
            continue
        if not isinstance(profile, dict):
            continue
        blockers = service.approval_blockers(profile)
        if TARGET_BLOCKERS & set(blockers):
            cohort[str(path)] = blockers
    COHORT_PATH.write_text(json.dumps(cohort, indent=1, sort_keys=True))
    return cohort


def load_progress() -> dict:
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text())
    return {}


def save_progress(progress: dict) -> None:
    tmp = PROGRESS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(progress, indent=1, sort_keys=True))
    tmp.replace(PROGRESS_PATH)


async def hold_jobs(paths: list[str]) -> tuple[int, set[str]]:
    async with connect_database() as conn:
        running = await conn.fetch(
            "SELECT profile_path FROM profile_jobs WHERE profile_path = ANY($1) AND status = 'running'",
            paths,
        )
        held = await conn.fetch(
            """
            UPDATE profile_jobs
            SET next_attempt_at = now() + interval '2 days',
                last_summary = coalesce(last_summary, '{}'::jsonb)
                    || '{"recovery_hold": true}'::jsonb,
                updated_at = now()
            WHERE profile_path = ANY($1) AND status IN ('pending', 'retry')
            RETURNING profile_path
            """,
            paths,
        )
    return len(held), {row["profile_path"] for row in running}


async def release_job(rel: str, *, promoted: bool, blocker_count: int | None) -> None:
    async with connect_database() as conn:
        if promoted:
            await conn.execute(
                """
                UPDATE profile_jobs
                SET status = 'promoted', next_attempt_at = now(),
                    last_summary = coalesce(last_summary, '{}'::jsonb)
                        || '{"recovery_promoted": true}'::jsonb,
                    updated_at = now()
                WHERE profile_path = $1 AND status IN ('pending', 'retry')
                """,
                rel,
            )
        else:
            await conn.execute(
                """
                UPDATE profile_jobs
                SET next_attempt_at = now(), priority = $2, updated_at = now()
                WHERE profile_path = $1 AND status IN ('pending', 'retry')
                """,
                rel,
                queue.priority_for_blocker_count(blocker_count or 0),
            )


async def unhold_jobs(paths: list[str]) -> None:
    async with connect_database() as conn:
        await conn.execute(
            """
            UPDATE profile_jobs SET next_attempt_at = now(), updated_at = now()
            WHERE profile_path = ANY($1) AND status IN ('pending', 'retry')
            """,
            paths,
        )


async def amain(args) -> dict:
    cohort = (
        json.loads(COHORT_PATH.read_text())
        if COHORT_PATH.exists() and not args.rebuild_cohort
        else build_cohort()
    )
    progress = load_progress()
    todo = [p for p in sorted(cohort) if p not in progress]
    if args.sample:
        todo = todo[: args.sample]
    held_count, active_elsewhere = (0, set())
    if not args.no_hold:
        held_count, active_elsewhere = await hold_jobs(todo)
    summary = {
        "cohort_total": len(cohort),
        "already_done": len(progress),
        "todo_this_run": len(todo),
        "held_jobs": held_count,
        "active_elsewhere": sorted(active_elsewhere),
        "processed": 0,
        "recovered_profiles": 0,
        "stat_recovered": 0,
        "ability_recovered": 0,
        "promoted": 0,
        "clean_unstamped": 0,
        "identity_mismatches": 0,
        "errors": 0,
        "llm_profiles": 0,
        "llm_disabled_wedge": False,
        "parser_counts": {},
        "promoted_paths": [],
    }
    llm_walls: list[float] = []
    processed_paths: list[str] = []
    try:
        for rel in todo:
            if rel in active_elsewhere:
                progress[rel] = {"skipped": "active_elsewhere"}
                save_progress(progress)
                continue
            path = Path(rel)
            try:
                rep = await auto_repair.recover_profile_evidence(
                    path,
                    notes_path=service.DEFAULT_REVIEW_NOTES_PATH,
                    max_sources=args.max_sources,
                )
            except Exception as exc:  # noqa: BLE001 - per-profile isolation
                progress[rel] = {"error": f"{type(exc).__name__}: {exc}"}
                save_progress(progress)
                summary["errors"] += 1
                await release_job(rel, promoted=False, blocker_count=len(cohort[rel]))
                continue
            profile = rep.pop("profile", None)
            promoted = False
            if not rep["blockers_after"]:
                if (
                    profile is not None
                    and profile.get("battle_eligible")
                    and profile.get("status") in {"provisional", "verified"}
                ):
                    approval = service.approve_profile(
                        path,
                        needs_review_dir=service.DEFAULT_NEEDS_REVIEW_DIR,
                        generated_dir=service.DEFAULT_GENERATED_DIR,
                        notes_path=service.DEFAULT_REVIEW_NOTES_PATH,
                        approved_by="auto_repair",
                    )
                    promoted = bool(approval.get("ok"))
                    if not promoted:
                        rep["approve_error"] = approval.get("error")
                else:
                    summary["clean_unstamped"] += 1
            recovered = rep.get("recovered_fields") or []
            entry = {
                "recovered_fields": recovered,
                "parser_used": rep.get("parser_used"),
                "blockers_before": rep.get("blockers_before"),
                "blockers_after": rep.get("blockers_after"),
                "promoted": promoted,
                "identity_mismatch": bool(rep.get("identity_mismatch")),
                "error": rep.get("error") or "",
                "wall_seconds": rep.get("wall_seconds"),
                "scoped_key": rep.get("scoped_key"),
                "sources_tried": rep.get("sources_tried"),
                "guard_rejections": rep.get("guard_rejections"),
                "merges": rep.get("merges"),
            }
            progress[rel] = entry
            save_progress(progress)
            processed_paths.append(rel)
            summary["processed"] += 1
            if recovered:
                summary["recovered_profiles"] += 1
            if any(f in recovered for f in ("attack_potency", "speed", "durability", "tier")):
                summary["stat_recovered"] += 1
            if "abilities" in recovered:
                summary["ability_recovered"] += 1
            if promoted:
                summary["promoted"] += 1
                summary["promoted_paths"].append(rel)
            if rep.get("identity_mismatch"):
                summary["identity_mismatches"] += 1
            for parser in rep.get("parser_used") or []:
                if parser:
                    summary["parser_counts"][parser] = summary["parser_counts"].get(parser, 0) + 1
            if "llm" in (rep.get("parser_used") or []):
                summary["llm_profiles"] += 1
                llm_walls.append(float(rep.get("wall_seconds") or 0))
                if (
                    len(llm_walls) >= 5
                    and statistics.median(llm_walls[-5:]) > WEDGE_MEDIAN_SECONDS
                    and os.environ.get("HARVEST_LLM_FALLBACK") == "1"
                ):
                    os.environ["HARVEST_LLM_FALLBACK"] = "0"
                    summary["llm_disabled_wedge"] = True
                    print("WEDGE: LLM median wall > threshold; LLM fallback disabled, continuing parser-only", flush=True)
            await release_job(
                rel,
                promoted=promoted,
                blocker_count=len(rep.get("blockers_after") or []),
            )
            print(
                f"[{summary['processed']}/{len(todo)}] {rel} recovered={recovered} "
                f"promoted={promoted} wall={rep.get('wall_seconds')}s",
                flush=True,
            )
    finally:
        untouched = [p for p in todo if p not in processed_paths and progress.get(p, {}).get("skipped") != "active_elsewhere"]
        if untouched and not args.no_hold:
            await unhold_jobs(untouched)
    if summary["promoted"]:
        imported = await queue_worker.import_generated_profiles(
            service.DEFAULT_GENERATED_DIR, database_url=database_url()
        )
        summary["imported"] = imported
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--rebuild-cohort", action="store_true")
    parser.add_argument("--no-hold", action="store_true")
    parser.add_argument("--max-sources", type=int, default=3)
    args = parser.parse_args()
    started = time.time()
    summary = asyncio.run(amain(args))
    summary["elapsed_seconds"] = round(time.time() - started, 1)
    if not args.sample:
        RESULTS_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
