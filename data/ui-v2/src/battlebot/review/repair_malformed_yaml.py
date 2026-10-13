"""Quarantine malformed generated and needs_review profile YAML files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from battlebot.profiles import yaml_io
from battlebot.review import service


def scan_profile_dirs(generated_dir: Path, needs_review_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for root in (generated_dir, needs_review_dir):
        if root.exists():
            paths.extend(sorted(root.rglob("*.yaml")))
    return paths


def repair_malformed_yaml(
    *,
    generated_dir: Path = service.DEFAULT_GENERATED_DIR,
    needs_review_dir: Path = service.DEFAULT_NEEDS_REVIEW_DIR,
    quarantine_dir: Path = yaml_io.DEFAULT_MALFORMED_QUARANTINE_DIR,
    report_path: Path | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_dir": str(generated_dir),
        "needs_review_dir": str(needs_review_dir),
        "quarantine_dir": str(quarantine_dir),
        "scanned": 0,
        "quarantined": 0,
        "ok": [],
        "malformed": [],
        "errors": [],
    }
    for path in scan_profile_dirs(generated_dir, needs_review_dir):
        report["scanned"] += 1
        try:
            yaml_io.load_yaml(path)
            report["ok"].append(str(path))
        except Exception as exc:  # noqa: BLE001 - keep scanning and report every bad file.
            if not yaml_io.is_yaml_parse_error(exc):
                report["errors"].append({"path": str(path), "error": str(exc), "error_type": type(exc).__name__})
                continue
            try:
                result = yaml_io.quarantine_file(path, error=exc, quarantine_dir=quarantine_dir)
            except Exception as quarantine_exc:  # noqa: BLE001 - keep scanning.
                report["errors"].append(
                    {
                        "path": str(path),
                        "error": str(quarantine_exc),
                        "error_type": type(quarantine_exc).__name__,
                    }
                )
                continue
            report["quarantined"] += 1
            report["malformed"].append(
                {
                    "source_path": str(result.source_path),
                    "quarantine_path": str(result.quarantine_path),
                    "report_path": str(result.report_path),
                    "error": result.error,
                }
            )
    target_report = report_path or (quarantine_dir / "repair_malformed_yaml_report.json")
    target_report.parent.mkdir(parents=True, exist_ok=True)
    report["report_path"] = str(target_report)
    target_report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quarantine malformed generated and needs_review YAML files")
    parser.add_argument("--generated-dir", type=Path, default=service.DEFAULT_GENERATED_DIR)
    parser.add_argument("--needs-review-dir", type=Path, default=service.DEFAULT_NEEDS_REVIEW_DIR)
    parser.add_argument("--quarantine-dir", type=Path, default=yaml_io.DEFAULT_MALFORMED_QUARANTINE_DIR)
    parser.add_argument("--report", type=Path, default=None)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    report = repair_malformed_yaml(
        generated_dir=args.generated_dir,
        needs_review_dir=args.needs_review_dir,
        quarantine_dir=args.quarantine_dir,
        report_path=args.report,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
