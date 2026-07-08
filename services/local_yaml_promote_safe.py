from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from datetime import datetime

import yaml

REQUIRED = [
    "name",
    "franchise",
    "attack_potency",
    "speed",
    "durability",
    "abilities",
]

BLOCK_WORDS = [
    "composite",
    "crossover",
    "non-canon",
    "non canon",
    "fanon",
    "joke",
]


def safe_slug(path: Path) -> str:
    return path.stem


def has_value(v) -> bool:
    return v not in (None, "", [], {})


def is_safe_profile(path: Path, data: dict) -> tuple[bool, str]:
    if data.get("needs_human_source_choice") is True:
        return False, "needs_human_source_choice_true"

    blob = (path.as_posix() + "\n" + str(data)).casefold()
    if any(w in blob for w in BLOCK_WORDS):
        return False, "blocked_version_word"

    missing = [k for k in REQUIRED if not has_value(data.get(k))]
    if missing:
        return False, "missing:" + ",".join(missing)

    abilities = data.get("abilities")
    if isinstance(abilities, list) and len(abilities) < 2:
        return False, "too_few_abilities"

    return True, "safe_local_yaml"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    src_root = Path("profiles/needs_review")
    dst_root = Path("profiles/generated")
    backup_root = Path("backups/local_yaml_promote") / datetime.now().strftime("%Y%m%d_%H%M%S")
    report = Path("logs/promote/local_yaml_promote_report.txt")
    report.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    promoted = 0

    for src in sorted(src_root.rglob("*.yaml")):
        if promoted >= args.limit:
            break

        try:
            data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            rows.append(f"SKIP {src} parse_error:{exc}")
            continue

        ok, reason = is_safe_profile(src, data)
        if not ok:
            rows.append(f"SKIP {src} {reason}")
            continue

        rel = src.relative_to(src_root)
        dst = dst_root / rel
        backup = backup_root / rel

        rows.append(f"{'PROMOTE' if args.apply else 'WOULD_PROMOTE'} {src} -> {dst} {reason}")

        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            backup.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src, backup)
            shutil.move(str(src), str(dst))

        promoted += 1

    summary = [
        f"apply={args.apply}",
        f"limit={args.limit}",
        f"promoted_or_would_promote={promoted}",
        "",
        *rows[:300],
    ]

    report.write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(report.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
