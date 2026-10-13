"""Read-only audit for duplicate or overlapping character profiles."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from battlebot.common.db import connect_database


DEFAULT_REPORT_PATH = Path("data/reports/duplicate_character_audit.json")
DEFAULT_PLAN_PATH = Path("data/reports/duplicate_character_apply_plan.json")
CONTINUITY_SUFFIXES = (
    "marvel comics",
    "dc comics",
    "earth 616",
    "earth 0",
    "prime earth",
    "new earth",
    "post crisis",
    "pre crisis",
    "marvel cinematic universe",
    "main continuity",
    "classic",
    "modern",
    "composite",
    "game",
    "movie",
    "mcu",
)
AMBIGUOUS_TITLE_ROOTS = ("captain marvel", "green lantern")
HIGH_TRUST_STATUSES = ("verified", "approved_override", "approved")
LOW_TRUST_STATUSES = ("needs_review", "auto_generated", "generated")
GENERIC_FRANCHISE_MARKERS = ("crossover", "mixed", "icons", "unknown", "user requests", "")


@dataclass(frozen=True)
class ProfileRecord:
    source: str
    profile_path: str
    canonical_name: str
    franchise: str
    category: str
    status: str
    profile_id: str = ""
    character_id: str = ""
    battle_eligible: bool = False
    is_user_request: bool = False
    sources: tuple[str, ...] = ()


def normalized_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", str(value or ""))
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = folded.replace("Earth-616", "Earth 616").replace("Earth-0", "Earth 0")
    text = re.sub(r"[^a-z0-9]+", " ", folded.casefold())
    return re.sub(r"\s+", " ", text).strip()


def strip_parenthetical_suffix(value: str) -> str:
    text = str(value or "").strip()
    while True:
        match = re.search(r"\s*\(([^)]*)\)\s*$", text)
        if not match:
            return text
        marker = normalized_text(match.group(1))
        if marker not in CONTINUITY_SUFFIXES:
            return text
        text = text[: match.start()].strip()


def strip_trailing_suffix_tokens(value: str) -> tuple[str, list[str]]:
    text = normalized_text(value)
    stripped: list[str] = []
    changed = True
    while changed:
        changed = False
        for suffix in sorted(CONTINUITY_SUFFIXES, key=lambda item: len(item.split()), reverse=True):
            suffix_tokens = suffix.split()
            tokens = text.split()
            if len(tokens) > len(suffix_tokens) and tokens[-len(suffix_tokens) :] == suffix_tokens:
                text = " ".join(tokens[: -len(suffix_tokens)])
                stripped.append(suffix)
                changed = True
                break
    return text, stripped


def normalized_base_identity(name: str) -> tuple[str, list[str]]:
    parenthetical_stripped = strip_parenthetical_suffix(name)
    base, stripped = strip_trailing_suffix_tokens(parenthetical_stripped)
    return base, stripped


def cluster_key_for_name(name: str) -> tuple[str, list[str], bool]:
    base, stripped = normalized_base_identity(name)
    for root in AMBIGUOUS_TITLE_ROOTS:
        if base == root or base.startswith(f"{root} "):
            return root, stripped, True
    return base, stripped, False


def is_user_request_profile(path: Path, data: dict[str, Any]) -> bool:
    if "/user-requests/" in path.as_posix():
        return True
    if str(data.get("franchise") or "").casefold() == "user requests":
        return True
    blockers = {str(blocker) for blocker in data.get("approval_blockers") or []}
    generation = data.get("generation") if isinstance(data.get("generation"), dict) else {}
    ineligible = {str(reason) for reason in generation.get("ineligible_reasons") or []}
    return "user_request_skeleton_schema_incomplete" in blockers or "queued_user_request" in ineligible


def record_from_yaml(path: Path, root_kind: str) -> ProfileRecord:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        data = {}
    return ProfileRecord(
        source=root_kind,
        profile_path=path.as_posix(),
        canonical_name=str(data.get("name") or path.stem),
        franchise=str(data.get("franchise") or ""),
        category=str(data.get("category") or ""),
        status=str(data.get("status") or root_kind),
        profile_id=str(data.get("id") or ""),
        character_id=str(data.get("character_id") or data.get("id") or ""),
        battle_eligible=bool(data.get("battle_eligible")),
        is_user_request=is_user_request_profile(path, data),
        sources=(root_kind,),
    )


def scan_yaml_profiles(root: Path, source: str) -> list[ProfileRecord]:
    if not root.exists():
        return []
    paths = sorted(root.rglob("*.yaml")) if root.is_dir() else [root]
    records = []
    for path in paths:
        try:
            records.append(record_from_yaml(path, source))
        except (OSError, yaml.YAMLError):
            continue
    return records


def record_summary(record: ProfileRecord) -> dict[str, Any]:
    return {
        "source": record.source,
        "sources": list(record.sources or (record.source,)),
        "profile_path": record.profile_path,
        "canonical_name": record.canonical_name,
        "franchise": record.franchise,
        "category": record.category,
        "status": record.status,
        "profile_id": record.profile_id,
        "character_id": record.character_id,
        "battle_eligible": record.battle_eligible,
    }


def profile_summary_path(profile: dict[str, Any]) -> str:
    return str(profile.get("profile_path") or "")


def profile_sources(profile: dict[str, Any]) -> set[str]:
    return {str(source) for source in profile.get("sources") or [profile.get("source") or ""] if source}


def source_family(source: str) -> str:
    return "db" if str(source).startswith("db:") else str(source)


def profile_identity_keys(record: ProfileRecord) -> list[tuple[str, ...]]:
    keys: list[tuple[str, ...]] = []
    if record.profile_id:
        keys.append(("profile_id", record.profile_id))
    if record.character_id and record.profile_path:
        keys.append(("character_path", record.character_id, record.profile_path))
    if record.profile_path:
        keys.append(("path", record.profile_path))
    fallback = (
        "name_context_source",
        normalized_text(record.canonical_name),
        normalized_text(record.franchise),
        normalized_text(record.category),
        source_family(record.source),
    )
    keys.append(fallback)
    return keys


def records_can_merge(left: ProfileRecord, right: ProfileRecord, key: tuple[str, ...]) -> bool:
    if key[0] in {"path", "character_path", "name_context_source"}:
        return True
    if key[0] == "profile_id":
        if left.profile_path and right.profile_path and left.profile_path == right.profile_path:
            return True
        return source_family(left.source) == "db" or source_family(right.source) == "db"
    return False


def merge_records(left: ProfileRecord, right: ProfileRecord) -> ProfileRecord:
    sources = tuple(sorted({*(left.sources or (left.source,)), *(right.sources or (right.source,))}))
    statuses = sorted({left.status, right.status} - {""})
    return ProfileRecord(
        source=sources[0] if sources else left.source,
        sources=sources,
        profile_path=left.profile_path or right.profile_path,
        canonical_name=left.canonical_name or right.canonical_name,
        franchise=left.franchise or right.franchise,
        category=left.category or right.category,
        status="/".join(statuses),
        profile_id=left.profile_id or right.profile_id,
        character_id=left.character_id or right.character_id,
        battle_eligible=bool(left.battle_eligible or right.battle_eligible),
        is_user_request=bool(left.is_user_request or right.is_user_request),
    )


def dedupe_records(records: list[ProfileRecord]) -> list[ProfileRecord]:
    distinct: list[ProfileRecord] = []
    key_index: dict[tuple[str, ...], int] = {}
    for record in records:
        normalized_record = record
        if not normalized_record.sources:
            normalized_record = ProfileRecord(
                source=record.source,
                sources=(record.source,),
                profile_path=record.profile_path,
                canonical_name=record.canonical_name,
                franchise=record.franchise,
                category=record.category,
                status=record.status,
                profile_id=record.profile_id,
                character_id=record.character_id,
                battle_eligible=record.battle_eligible,
                is_user_request=record.is_user_request,
            )
        keys = profile_identity_keys(normalized_record)
        match_index = None
        for key in keys:
            candidate_index = key_index.get(key)
            if candidate_index is not None and records_can_merge(distinct[candidate_index], normalized_record, key):
                match_index = candidate_index
                break
        if match_index is None:
            key_index.update({key: len(distinct) for key in keys})
            distinct.append(normalized_record)
            continue
        merged = merge_records(distinct[match_index], normalized_record)
        distinct[match_index] = merged
        for key in profile_identity_keys(merged):
            key_index[key] = match_index
    return distinct


def has_generated_needs_review_overlap(records: list[ProfileRecord]) -> bool:
    sources_by_name: dict[str, set[str]] = {}
    for record in records:
        sources = set(record.sources or (record.source,))
        sources_by_name.setdefault(normalized_text(record.canonical_name), set()).update(sources)
    return any({"generated", "needs_review"}.issubset(sources) for sources in sources_by_name.values())


def suggested_action(records: list[ProfileRecord], *, ambiguous_root: bool, variant_markers: set[str]) -> str:
    franchises = {normalized_text(record.franchise) for record in records if record.franchise}
    categories = {normalized_text(record.category) for record in records if record.category}
    names = {normalized_text(record.canonical_name) for record in records if record.canonical_name}
    if ambiguous_root:
        return "review_variant_split"
    if len(franchises) > 1 or len(categories) > 1:
        return "review_variant_split"
    if has_generated_needs_review_overlap(records):
        return "likely_bad_duplicate"
    if variant_markers:
        return "review_variant_split"
    if len(names) == 1:
        return "merge_duplicate"
    return "likely_bad_duplicate"


def cluster_reason(cluster_key: str, records: list[ProfileRecord], variant_markers: set[str], ambiguous_root: bool) -> str:
    if ambiguous_root:
        return f"shared ambiguous title root '{cluster_key}' requires manual variant split review"
    if variant_markers:
        return f"same base identity after stripping suffixes: {', '.join(sorted(variant_markers))}"
    names = sorted({record.canonical_name for record in records})
    return f"same normalized base identity across {len(names)} profile names"


def audit_records(records: list[ProfileRecord], *, min_cluster_size: int = 2, include_user_requests: bool = False) -> dict[str, Any]:
    raw_count = len(records)
    records = dedupe_records(records)
    buckets: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.is_user_request and not include_user_requests:
            continue
        key, stripped, ambiguous_root = cluster_key_for_name(record.canonical_name)
        if not key:
            continue
        bucket = buckets.setdefault(
            key,
            {"records": [], "variant_markers": set(), "ambiguous_root": ambiguous_root},
        )
        bucket["records"].append(record)
        bucket["variant_markers"].update(stripped)
        bucket["ambiguous_root"] = bool(bucket["ambiguous_root"] or ambiguous_root)

    clusters = []
    for key, bucket in sorted(buckets.items()):
        bucket_records = sorted(bucket["records"], key=lambda item: (item.franchise, item.category, item.canonical_name, item.profile_path))
        if len(bucket_records) < min_cluster_size:
            continue
        variant_markers = set(bucket["variant_markers"])
        ambiguous_root = bool(bucket["ambiguous_root"])
        clusters.append(
            {
                "cluster_key": key,
                "profile_paths": sorted({record.profile_path for record in bucket_records if record.profile_path}),
                "canonical_names": sorted({record.canonical_name for record in bucket_records if record.canonical_name}),
                "franchises": sorted({record.franchise for record in bucket_records if record.franchise}),
                "categories": sorted({record.category for record in bucket_records if record.category}),
                "statuses": sorted({record.status for record in bucket_records if record.status}),
                "profiles": [record_summary(record) for record in bucket_records],
                "reason": cluster_reason(key, bucket_records, variant_markers, ambiguous_root),
                "suggested_action": suggested_action(
                    bucket_records,
                    ambiguous_root=ambiguous_root,
                    variant_markers=variant_markers,
                ),
            }
        )
    action_counts = {
        "likely_bad_duplicate": 0,
        "review_variant_split": 0,
        "merge_duplicate": 0,
        "keep_all_variants": 0,
    }
    for cluster in clusters:
        action = str(cluster.get("suggested_action") or "")
        if action in action_counts:
            action_counts[action] += 1
    return {
        "summary": {
            "raw_records_scanned": raw_count,
            "distinct_profiles_scanned": len(records),
            "profiles_scanned": len(records),
            "clusters": len(clusters),
            **action_counts,
        },
        "clusters": clusters,
    }


def profile_completeness_score(profile: dict[str, Any]) -> int:
    score = 0
    if profile.get("battle_eligible"):
        score += 3
    if profile.get("canonical_name"):
        score += 1
    if profile.get("franchise"):
        score += 1
    if profile.get("category"):
        score += 1
    if profile.get("profile_path"):
        score += 1
    return score


def status_priority(profile: dict[str, Any]) -> int:
    status = normalized_text(str(profile.get("status") or ""))
    if "verified" in status:
        return 50
    if "approved override" in status or "approved" in status:
        return 40
    if profile.get("battle_eligible") and "generated" in profile_sources(profile):
        return 35
    if "auto generated" in status or "generated" in status:
        return 25
    if "needs review" in status or "needs_review" in status:
        return 10
    return 0


def franchise_specificity_score(profile: dict[str, Any]) -> int:
    franchise = normalized_text(str(profile.get("franchise") or ""))
    category = normalized_text(str(profile.get("category") or ""))
    if any(marker and marker in franchise for marker in GENERIC_FRANCHISE_MARKERS):
        return 0
    if category in {"mixed", "crossover"}:
        return 1
    return 3 if franchise else 0


def keep_profile_sort_key(profile: dict[str, Any]) -> tuple[int, int, int, int]:
    path = profile_summary_path(profile)
    return (
        status_priority(profile),
        franchise_specificity_score(profile),
        profile_completeness_score(profile),
        -len(path),
    )


def choose_keep_profile(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    return max(profiles, key=keep_profile_sort_key)


def cluster_has_status_conflict(profiles: list[dict[str, Any]]) -> bool:
    high = any(any(status in normalized_text(str(profile.get("status") or "")) for status in HIGH_TRUST_STATUSES) for profile in profiles)
    low = any(any(status in normalized_text(str(profile.get("status") or "")) for status in LOW_TRUST_STATUSES) for profile in profiles)
    return high and low and len({normalized_text(str(profile.get("status") or "")) for profile in profiles}) > 2


def safety_level_for_cluster(cluster: dict[str, Any], keep_profile: dict[str, Any]) -> str:
    profiles = list(cluster.get("profiles") or [])
    franchises = {normalized_text(str(profile.get("franchise") or "")) for profile in profiles}
    categories = {normalized_text(str(profile.get("category") or "")) for profile in profiles}
    if len(franchises) > 1 or len(categories) > 1:
        return "manual_review"
    if cluster_has_status_conflict(profiles):
        return "manual_review"
    keep_sources = profile_sources(keep_profile)
    archive_sources = set().union(*(profile_sources(profile) for profile in profiles if profile is not keep_profile))
    if {"generated", "needs_review"}.issubset(keep_sources | archive_sources) and (
        "generated" in keep_sources or keep_profile.get("battle_eligible")
    ):
        return "safe_auto_archive"
    generated_count = sum(1 for profile in profiles if "generated" in profile_sources(profile))
    if generated_count > 1:
        return "cautious_review"
    return "cautious_review"


def plan_reason(cluster: dict[str, Any], keep_profile: dict[str, Any], safety_level: str) -> str:
    keep_name = keep_profile.get("canonical_name") or keep_profile.get("profile_path") or "selected profile"
    if safety_level == "safe_auto_archive":
        return (
            f"Keep {keep_name}: same franchise/category/base identity, with generated or battle-ready coverage "
            "beating needs_review duplicate records."
        )
    if safety_level == "manual_review":
        return f"Manual review required for {cluster['cluster_key']}: cross-franchise/category or status conflict could indicate real variants."
    return f"Keep {keep_name} for now, but review before archiving because multiple generated or versioned profiles may be meaningful."


def build_apply_plan(report: dict[str, Any]) -> dict[str, Any]:
    actions = []
    for cluster in report.get("clusters") or []:
        profiles = list(cluster.get("profiles") or [])
        action = str(cluster.get("suggested_action") or "")
        if action == "review_variant_split":
            actions.append(
                {
                    "cluster_key": cluster.get("cluster_key"),
                    "action": "manual_review",
                    "keep_profile": None,
                    "archive_profiles": [],
                    "reason": "Variant split clusters are never auto-archived by the duplicate audit plan.",
                    "safety_level": "manual_review",
                    "profiles": profiles,
                }
            )
            continue
        if action != "likely_bad_duplicate" or not profiles:
            continue
        keep_profile = choose_keep_profile(profiles)
        keep_path = profile_summary_path(keep_profile)
        archive_profiles = [profile for profile in profiles if profile_summary_path(profile) != keep_path]
        safety = safety_level_for_cluster(cluster, keep_profile)
        if safety == "manual_review":
            archive_profiles = []
        actions.append(
            {
                "cluster_key": cluster.get("cluster_key"),
                "action": "archive_duplicates" if archive_profiles else "manual_review",
                "keep_profile": keep_profile,
                "archive_profiles": archive_profiles,
                "reason": plan_reason(cluster, keep_profile, safety),
                "safety_level": safety,
                "profiles": profiles,
            }
        )
    counts = {"safe_auto_archive": 0, "cautious_review": 0, "manual_review": 0}
    for action in actions:
        safety = str(action.get("safety_level") or "")
        if safety in counts:
            counts[safety] += 1
    return {
        "summary": {
            "clusters_considered": len(report.get("clusters") or []),
            "actions": len(actions),
            **counts,
        },
        "actions": actions,
    }


def format_apply_plan_dry_run(plan: dict[str, Any]) -> str:
    lines = ["duplicate apply-plan dry run"]
    for action in plan.get("actions") or []:
        archive_profiles = action.get("archive_profiles") or []
        if not archive_profiles:
            continue
        keep = action.get("keep_profile") or {}
        lines.append(f"- {action['cluster_key']}: keep {profile_summary_path(keep)}")
        for profile in archive_profiles:
            lines.append(f"  would archive: {profile_summary_path(profile)}")
    if len(lines) == 1:
        lines.append("- no archive candidates")
    return "\n".join(lines)


async def fetch_db_records(database_url: str | None) -> list[ProfileRecord]:
    if not database_url:
        return []
    async with connect_database(database_url) as connection:
        rows = await connection.fetch(
            """
SELECT
    cp.profile_id,
    cp.character_id,
    cp.profile_path,
    cp.status,
    cp.battle_eligible,
    c.canonical_name,
    c.franchise,
    c.category
FROM character_profiles cp
JOIN characters c ON c.id = cp.character_id
"""
        )
        records = [
            ProfileRecord(
                source="db:character_profiles",
                profile_path=str(dict(row).get("profile_path") or ""),
                canonical_name=str(dict(row).get("canonical_name") or ""),
                franchise=str(dict(row).get("franchise") or ""),
                category=str(dict(row).get("category") or ""),
                status=str(dict(row).get("status") or ""),
                profile_id=str(dict(row).get("profile_id") or ""),
                character_id=str(dict(row).get("character_id") or ""),
                battle_eligible=bool(dict(row).get("battle_eligible")),
                sources=("db:character_profiles",),
            )
            for row in rows
        ]
        try:
            review_rows = await connection.fetch(
                """
SELECT
    profile_id,
    profile_path,
    status,
    profile_json
FROM review_profiles
"""
            )
        except Exception:  # noqa: BLE001 - optional table may not exist in older installs.
            review_rows = []
        for row in review_rows:
            data = dict(row)
            profile_json = data.get("profile_json") if isinstance(data.get("profile_json"), dict) else {}
            records.append(
                ProfileRecord(
                    source="db:review_profiles",
                    profile_path=str(data.get("profile_path") or ""),
                    canonical_name=str(profile_json.get("name") or data.get("profile_id") or ""),
                    franchise=str(profile_json.get("franchise") or ""),
                    category=str(profile_json.get("category") or ""),
                    status=str(data.get("status") or profile_json.get("status") or ""),
                    profile_id=str(data.get("profile_id") or ""),
                    character_id=str(profile_json.get("character_id") or profile_json.get("id") or ""),
                    battle_eligible=bool(profile_json.get("battle_eligible")),
                    sources=("db:review_profiles",),
                )
            )
    return records


def format_summary(report: dict[str, Any]) -> str:
    clusters = report.get("clusters") or []
    lines = [f"duplicate character clusters: {len(clusters)}"]
    if not clusters:
        lines.append("- none")
        return "\n".join(lines)
    for cluster in clusters:
        lines.append(
            f"- {cluster['cluster_key']} ({len(cluster['profiles'])}): {cluster['suggested_action']} - {cluster['reason']}"
        )
        for profile in cluster["profiles"][:6]:
            lines.append(
                f"  {profile['canonical_name']} [{profile['franchise']}/{profile['category']}/{profile['status']}] {profile['profile_path']}"
            )
    return "\n".join(lines)


async def build_report(args: argparse.Namespace) -> dict[str, Any]:
    records = []
    source = str(getattr(args, "source", "all") or "all")
    if source in {"generated", "all"}:
        records.extend(scan_yaml_profiles(args.generated_dir, "generated"))
    if source in {"needs_review", "all"}:
        records.extend(scan_yaml_profiles(args.needs_review_dir, "needs_review"))
    if source in {"db", "all"}:
        records.extend(await fetch_db_records(args.database_url))
    return audit_records(
        records,
        min_cluster_size=max(1, int(args.min_cluster_size)),
        include_user_requests=bool(args.include_user_requests),
    )


def write_report(report: dict[str, Any], path: Path = DEFAULT_REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_plan(plan: dict[str, Any], path: Path = DEFAULT_PLAN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit duplicate or overlapping character profiles")
    parser.add_argument("--generated-dir", type=Path, default=Path("profiles/generated"))
    parser.add_argument("--needs-review-dir", type=Path, default=Path("profiles/needs_review"))
    parser.add_argument("--database-url")
    parser.add_argument("--source", choices=("generated", "needs_review", "db", "all"), default="all")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--write-plan", action="store_true")
    parser.add_argument("--apply-plan-dry-run", action="store_true")
    parser.add_argument("--min-cluster-size", type=int, default=2)
    parser.add_argument("--include-user-requests", action="store_true")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    report = await build_report(args)
    if args.write_report:
        write_report(report)
    plan = build_apply_plan(report)
    if args.write_plan:
        write_plan(plan)
    if args.apply_plan_dry_run:
        print(format_apply_plan_dry_run(plan))
        return 0
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else format_summary(report))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
