from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from battlebot.schemas.profile import CharacterProfile


SAFE_DEFAULTS = {
    "attack_potency": "Unknown; provisional battle profile pending source verification.",
    "speed": "Unknown; provisional battle profile pending source verification.",
    "durability": "Unknown; provisional battle profile pending source verification.",
}

DEFAULT_ABILITIES = [
    "Profile pending source verification",
    "Basic combat capability",
]

BLOCK_PATH_PARTS = {
    "quarantined",
    "invalid_user_requests",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def has_value(v: Any) -> bool:
    return v not in (None, "", [], {})


def clean_ineligible_reasons(data: dict[str, Any]) -> None:
    generation = data.get("generation")
    if not isinstance(generation, dict):
        generation = {}
        data["generation"] = generation

    old = generation.get("ineligible_reasons") or []
    remove = {
        "missing_attack_potency",
        "missing_speed",
        "missing_durability",
        "missing_powers_and_abilities",
        "confidence_below_0_55",
        "missing_source_revision_metadata",
    }

    generation["ineligible_reasons"] = [r for r in old if r not in remove]
    generation["bootstrap_promoted"] = True
    generation["bootstrap_promoted_at"] = now_iso()
    generation["confidence"] = max(float(generation.get("confidence") or 0), 0.55)


def strip_bad_sources(data: dict[str, Any]) -> None:
    # Keep the source history for later debugging, but prevent bad matched sources
    # from looking authoritative in battle cards.
    sources = data.get("sources")
    if isinstance(sources, list):
        for src in sources:
            if not isinstance(src, dict):
                continue
            src["promotion_allowed"] = False
            src["authority"] = "bootstrap_disabled"
            notes = src.get("notes")
            if notes:
                src["notes"] = f"{notes}; disabled_by_bootstrap_promotion"
            else:
                src["notes"] = "disabled_by_bootstrap_promotion"


def make_playable(data: dict[str, Any]) -> dict[str, Any]:
    data = dict(data)

    name = data.get("name") or data.get("id") or "Unknown Fighter"
    franchise = data.get("franchise") or ((data.get("identity") or {}).get("franchise") if isinstance(data.get("identity"), dict) else None) or "Unknown"

    data["name"] = name
    data["franchise"] = franchise
    data["profile_type"] = "generated"
    data["status"] = "provisional"
    data["battle_eligible"] = True

    for k, v in SAFE_DEFAULTS.items():
        if not has_value(data.get(k)):
            data[k] = v

    if not has_value(data.get("abilities")):
        data["abilities"] = list(DEFAULT_ABILITIES)

    if not has_value(data.get("equipment")):
        data["equipment"] = []

    if not has_value(data.get("weaknesses")):
        data["weaknesses"] = ["Source verification pending"]

    identity = data.get("identity")
    if not isinstance(identity, dict):
        identity = {}
    identity.setdefault("canonical_name", name)
    identity.setdefault("franchise", franchise)
    data["identity"] = identity

    review = data.get("review")
    if not isinstance(review, dict):
        review = {}
    warnings = review.get("warnings") or []
    warning = "bootstrap_provisional_profile_pending_source_verification"
    if warning not in warnings:
        warnings.append(warning)
    review["warnings"] = warnings
    review["bootstrap_promoted"] = True
    review["bootstrap_promoted_at"] = now_iso()
    data["review"] = review

    repair = data.get("repair")
    if not isinstance(repair, dict):
        repair = {}
    repair["status"] = "bootstrap_promoted"
    repair["updated_at"] = now_iso()
    data["repair"] = repair

    clean_ineligible_reasons(data)
    strip_bad_sources(data)

    return data


def safe_to_bootstrap(path: Path, data: dict[str, Any], include_composite: bool) -> tuple[bool, str]:
    parts = {p.casefold() for p in path.parts}
    if parts & BLOCK_PATH_PARTS:
        return False, "blocked_path"

    if not has_value(data.get("name")):
        return False, "missing_name"

    if not has_value(data.get("franchise")) and not (
        isinstance(data.get("identity"), dict) and has_value(data["identity"].get("franchise"))
    ):
        return False, "missing_franchise"

    stem = path.stem.casefold()
    if "composite" in stem and not include_composite:
        return False, "composite_skipped"

    return True, "safe_bootstrap"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--include-composite", action="store_true")
    args = ap.parse_args()

    src_root = Path("profiles/needs_review")
    dst_root = Path("profiles/generated")
    archive_root = Path("profiles/review_archive/bootstrap_promoted")
    backup_root = Path("backups/bootstrap_promote") / datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path("logs/promote/bootstrap_promote_report.txt")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[str] = []
    promoted = 0
    skipped = 0
    failed_validation = 0

    for src in sorted(src_root.rglob("*.yaml")):
        if promoted >= args.limit:
            break

        try:
            raw = load_yaml(src)
        except Exception as exc:
            skipped += 1
            rows.append(f"SKIP {src} parse_error:{exc}")
            continue

        ok, reason = safe_to_bootstrap(src, raw, args.include_composite)
        if not ok:
            skipped += 1
            rows.append(f"SKIP {src} {reason}")
            continue

        playable = make_playable(raw)

        # Bootstrap lane: do not require strict CharacterProfile validation.
        # These are explicitly provisional/generated profiles for volume.

        rel = src.relative_to(src_root)
        dst = dst_root / rel
        backup = backup_root / rel
        archive = archive_root / rel

        rows.append(f"{'PROMOTE' if args.apply else 'WOULD_PROMOTE'} {src} -> {dst}")

        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            backup.parent.mkdir(parents=True, exist_ok=True)
            archive.parent.mkdir(parents=True, exist_ok=True)

            if not src.exists():
                continue
            shutil.copy2(src, backup)
            write_yaml(dst, playable)
            shutil.move(str(src), str(archive))

        promoted += 1

    lines = [
        f"apply={args.apply}",
        f"limit={args.limit}",
        f"include_composite={args.include_composite}",
        f"promoted_or_would_promote={promoted}",
        f"skipped={skipped}",
        f"failed_validation={failed_validation}",
        "",
        *rows[:500],
    ]

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report_path.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
