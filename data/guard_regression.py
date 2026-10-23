"""Fix A guard regression: dry-run recovery on the 4 known-bad profiles.

Each profile's bad merge from the first Fix A run must now be REJECTED,
attributed to a specific guard. Korosensei's pre-run backup state is the
positive control: the guard must still let his correct recovery through.
Nothing is written (dry_run=True everywhere).
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app/src")
sys.path.insert(0, "/app")

from battlebot.review import auto_repair, service
from battlebot.review.auto_repair import boilerplate_reasons
from battlebot.review.providers import mediawiki

BAD_PAGES = {
    "profiles/needs_review/anime/dorohedoro/caiman.yaml": {
        "must_not_merge": ["Yacare Caiman", "Kaimen", "Hrugetaur"],
        "expect_reject_reasons": ["nonfiction", "name_mismatch", "franchise"],
    },
    "profiles/needs_review/anime/chainsaw-man/yoru.yaml": {
        "must_not_merge": ["Yoru (Valorant)", "Denji"],
        "expect_reject_reasons": ["franchise_no_evidence", "name_mismatch"],
    },
    "profiles/needs_review/anime/digimon/tai-kamiya.yaml": {
        "must_not_merge": [],
        "expect_reject_reasons": ["name_mismatch"],
        "boilerplate_source": "character-stats-profiles-tai-kamiya-digimon",
    },
    "profiles/needs_review/anime/claymore/galatea.yaml": {
        "must_not_merge": ["Galatea (DCAU)", "Teresa (Claymore)"],
        "expect_reject_reasons": ["franchise_no_evidence", "name_mismatch"],
    },
}


def summarize(rel, rep):
    print("=" * 100)
    print("PROFILE", rel)
    for tried in rep.get("sources_tried") or []:
        for attempt in tried.get("guard_attempts") or []:
            print(
                f"  GUARD source={tried.get('source_id')} fetched={attempt['fetched_title']!r} "
                f"via={attempt['via']} accepted={attempt['accepted']} "
                f"name_match={attempt['name_match']} channels={attempt['franchise_channels']} "
                f"nonfiction={attempt['nonfiction_hits']} reasons={attempt['reasons']}"
            )
        if tried.get("boilerplate_fields"):
            print(f"  BOILERPLATE source={tried.get('source_id')} fields={tried['boilerplate_fields']} {tried.get('boilerplate_reasons')}")
    for merge in rep.get("merges") or []:
        print(
            f"  MERGE source={merge['source_id']} page={merge['fetched_title']!r} "
            f"url={merge['fetched_url']} rev={merge['revision_id']} via={merge['via']} "
            f"channels={merge['franchise_channels']} fields={merge['recovered_fields']}"
        )
    print("  recovered_fields:", rep.get("recovered_fields"))
    print("  blockers_after:", rep.get("blockers_after"))
    return rep


async def main():
    failures = []
    for rel, spec in BAD_PAGES.items():
        rep = await auto_repair.recover_profile_evidence(Path("/app") / rel, dry_run=True)
        rep.pop("profile", None)
        summarize(rel, rep)
        merged_titles = [m["fetched_title"] for m in rep.get("merges") or []]
        for bad in spec["must_not_merge"]:
            if any(bad in title for title in merged_titles):
                failures.append(f"{rel}: BAD PAGE MERGED: {bad}")
        all_reasons = [
            reason
            for rej in rep.get("guard_rejections") or []
            for reason in rej["reasons"]
        ] + [
            reason
            for tried in rep.get("sources_tried") or []
            for attempt in tried.get("guard_attempts") or []
            for reason in attempt["reasons"]
        ]
        if not any(
            any(exp in reason for reason in all_reasons)
            for exp in spec["expect_reject_reasons"]
        ):
            failures.append(f"{rel}: no expected guard rejection found in {all_reasons}")
        if spec.get("boilerplate_source"):
            profile = service.load_yaml(Path("/app") / rel)
            src = next(
                s for s in profile.get("sources") or []
                if str(s.get("id")) == spec["boilerplate_source"]
            )
            fields0, meta = await mediawiki.fetch_mediawiki_fields(
                src, auto_repair.parse_source_content
            )
            reasons = boilerplate_reasons(fields0.get("attack_potency"), scalar=True)
            print(
                f"  BOILERPLATE-DIRECT source={spec['boilerplate_source']} "
                f"fetched={meta.get('title')!r} AP reasons={reasons} "
                f"AP text={str(fields0.get('attack_potency'))[:110]!r}"
            )
            if "template_instruction" not in reasons:
                failures.append(f"{rel}: boilerplate filter did not catch template AP")

    # Positive control: Korosensei pre-run state from the morning backup.
    rep = await auto_repair.recover_profile_evidence(
        Path("/app/data/tmp_regression/korosensei.yaml"), dry_run=True
    )
    rep.pop("profile", None)
    summarize("data/tmp_regression/korosensei.yaml (pre-run backup)", rep)
    if "abilities" not in (rep.get("recovered_fields") or []):
        failures.append("korosensei control: abilities NOT recovered")
    if not rep.get("merges"):
        failures.append("korosensei control: no merges at all")

    print("=" * 100)
    if failures:
        print("REGRESSION FAILURES:")
        for failure in failures:
            print(" -", failure)
        return 1
    print("REGRESSION SET: ALL BAD MERGES REJECTED, CONTROL RECOVERED")
    return 0


sys.exit(asyncio.run(main()))
