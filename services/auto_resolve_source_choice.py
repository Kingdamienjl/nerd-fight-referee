from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

TRUSTED = [
    "vsbattles",
    "vs battles",
    "character_stats_profiles",
    "character stats",
    "superherodb",
    "super hero db",
    "kaggle_superherodb",
    "kaggle",
]

DIRTY_VERSION_WORDS = [
    "composite",
    "non-canon",
    "non canon",
    "crossover",
    "joke",
    "fanon",
    "alternate",
    "what-if",
    "what if",
]


def walk_dicts(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk_dicts(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_dicts(item)


def has_source_choice_flag(data) -> bool:
    for d in walk_dicts(data):
        if d.get("needs_human_source_choice") is True:
            return True
    return False


def clear_source_choice_flags(data) -> int:
    changed = 0
    for d in walk_dicts(data):
        if d.get("needs_human_source_choice") is True:
            d["needs_human_source_choice"] = False
            d["source_choice_auto_resolved"] = True
            d["source_choice_auto_resolved_at"] = datetime.now().isoformat(timespec="seconds")
            changed += 1
    return changed


def text_blob(data) -> str:
    try:
        return json.dumps(data, ensure_ascii=False).casefold()
    except Exception:
        return str(data).casefold()


def is_dirty_version(data) -> bool:
    blob = text_blob(data)
    return any(w in blob for w in DIRTY_VERSION_WORDS)


def trusted_source_score(data) -> int:
    blob = text_blob(data)
    score = 0
    for i, source in enumerate(TRUSTED):
        if source in blob:
            score = max(score, 100 - i * 5)
    return score


def is_safe_to_resolve(data) -> tuple[bool, str]:
    if not has_source_choice_flag(data):
        return False, "no_source_choice_flag"

    if is_dirty_version(data):
        return False, "dirty_or_nondefault_version_word"

    score = trusted_source_score(data)
    if score < 70:
        return False, "no_trusted_source_signal"

    return True, f"trusted_source_score_{score}"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="profiles/needs_review")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    root = Path(args.root)
    report_path = Path("logs/source_choice/auto_resolve_source_choice_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted([p for p in root.rglob("*.json") if p.is_file()])
    rows = []
    changed = 0

    for path in files:
        if changed >= args.limit:
            break

        try:
            data = load_json(path)
        except Exception as exc:
            rows.append({"path": str(path), "action": "skip", "reason": f"parse_error:{exc}"})
            continue

        safe, reason = is_safe_to_resolve(data)

        if not has_source_choice_flag(data):
            continue

        if not safe:
            rows.append({"path": str(path), "action": "skip", "reason": reason})
            continue

        if args.apply:
            backup = Path("backups/source_choice") / path.relative_to(root)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)

            cleared = clear_source_choice_flags(data)
            save_json(path, data)

            rows.append({"path": str(path), "action": "resolved", "reason": reason, "cleared_flags": cleared})
            changed += 1
        else:
            rows.append({"path": str(path), "action": "would_resolve", "reason": reason})
            changed += 1

    summary = {
        "apply": args.apply,
        "limit": args.limit,
        "scanned_json_files": len(files),
        "candidate_actions": len(rows),
        "resolved_or_would_resolve": changed,
        "rows": rows[:200],
    }

    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps({
        "apply": args.apply,
        "scanned_json_files": len(files),
        "resolved_or_would_resolve": changed,
        "report": str(report_path),
    }, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
