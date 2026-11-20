"""Audit runner: cache audit + most-fought profile audit, one report.

Usage (one-off container on LXC 106, network referee_default,
--env-file /opt/referee/.env):

    python -m battlebot.audit.runner [--skip-rejudge]
        [--sample-cap 25] [--top-n 20] [--out-dir data/audit_reports]

Writes data/audit_reports/<YYYY-MM-DD>.md and prints a one-paragraph
summary to stdout. Read-only: no DB writes, no cache/profile
modifications. Exit 0 even when findings exist (findings are data,
not failure); exit 2 on infrastructure errors (DB unreachable, ...).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from battlebot.audit.cache_audit import audit_cache
from battlebot.audit.profile_audit import audit_top_profiles
from battlebot.common.db import connect_database

DEFAULT_REPORT_DIR = "data/audit_reports"


def repo_root() -> Path:
    """Repo root: .../src/battlebot/audit/runner.py -> parents[3]."""
    return Path(__file__).resolve().parents[3]


def _fights(n: int) -> str:
    return f"{n} fight" if n == 1 else f"{n} fights"


def _cap(items: list[str], limit: int = 5) -> str:
    shown = items[:limit]
    text = "; ".join(shown)
    if len(items) > limit:
        text += f"; …and {len(items) - limit} more"
    return text


async def run_audit(
    *,
    root: Path,
    sample_cap: int = 25,
    top_n: int = 20,
    rejudge: bool = True,
    caller: Any | None = None,
    report_date: str | None = None,
) -> dict[str, Any]:
    """Run both audit parts. Read-only."""
    date = report_date or datetime.now(UTC).strftime("%Y-%m-%d")
    async with connect_database() as conn:
        cache = await audit_cache(conn, sample_cap=sample_cap, rejudge=rejudge, caller=caller)
        profiles = await audit_top_profiles(conn, top_n=top_n, repo_root=root)
    counts = {
        "cache_rows_checked": cache["rows_checked"],
        "cache_checker_failed": len(cache["checker_failed"]),
        "cache_stale": len(cache["stale"]),
        "cache_rejudged": len(cache["rejudged"]),
        "cache_disagreements": len(cache["disagreements"]),
        "cache_rejudge_errors": len(cache["rejudge_errors"]),
        "profiles_ranked": profiles["ranked_total"],
        "profiles_audited": len(profiles["audited"]),
        "profiles_unresolved": len(profiles["unresolved"]),
        "profiles_flagged": len(profiles["flagged"]),
        "profiles_clean": profiles["clean"],
    }
    return {
        "date": date,
        "generated_at": datetime.now(UTC).isoformat(),
        "cache": cache,
        "profiles": profiles,
        "counts": counts,
    }


def format_report(results: dict[str, Any]) -> str:
    """Markdown report for data/audit_reports/<date>.md."""
    c = results["counts"]
    cache = results["cache"]
    prof = results["profiles"]
    lines = [
        f"# Referee audit — {results['date']}",
        "",
        (
            f"Generated {results['generated_at']} (UTC). Read-only audit: "
            "flags only, nothing modified."
        ),
        "",
        "## Counts",
        "",
        f"- Cache rows checked: {c['cache_rows_checked']}",
        f"- Cache checker failures: {c['cache_checker_failed']}",
        f"- Cache stale rows: {c['cache_stale']}",
        (
            f"- Cache re-judged: {c['cache_rejudged']} "
            f"({c['cache_disagreements']} disagreements, "
            f"{c['cache_rejudge_errors']} errors; "
            f"est. re-judge cost ${cache['est_cost_usd']:.4f})"
        ),
        f"- Profiles ranked: {c['profiles_ranked']}",
        (
            f"- Profiles audited (top {prof['top_n']}): "
            f"{c['profiles_audited']} ({c['profiles_clean']} clean, "
            f"{c['profiles_flagged']} flagged, "
            f"{c['profiles_unresolved']} unresolved)"
        ),
        "",
        "## Cache checker failures",
        "",
    ]
    for row in cache["checker_failed"]:
        lines.append(
            f"- row {row['row_id']} ({row['pair']}): "
            f"{', '.join(row['fail'])}"
            + (f" [flags: {'; '.join(row['flags'])}]" if row["flags"] else "")
        )
    if not cache["checker_failed"]:
        lines.append("- (none)")
    lines += ["", "## Cache stale rows", ""]
    for row in cache["stale"]:
        lines.append(f"- row {row['row_id']} ({row['pair']}): {', '.join(row['findings'])}")
    if not cache["stale"]:
        lines.append("- (none)")
    lines += ["", "## Cache re-judge disagreements", ""]
    for row in cache["disagreements"]:
        lines.append(f"- row {row['row_id']} ({row['pair']}): {'; '.join(row['disagreements'])}")
    if not cache["disagreements"]:
        lines.append("- (none)")
    lines += ["", "## Cache re-judge errors", ""]
    for row in cache["rejudge_errors"]:
        lines.append(f"- row {row['row_id']} ({row['pair']}): {row['error']}")
    if not cache["rejudge_errors"]:
        lines.append("- (none)")
    lines += ["", "## Flagged profiles (top most-fought)", ""]
    for f in prof["flagged"]:
        bits = []
        if f["blockers"]:
            bits.append("blockers: " + ", ".join(f["blockers"]))
        if f["missing_core_fields"]:
            bits.append("missing: " + ", ".join(f["missing_core_fields"]))
        if f["debris"]:
            bits.append("debris: " + _cap(f["debris"]))
        if f["yaml"]:
            bits.append("yaml: " + "; ".join(f["yaml"]))
        lines.append(
            f"- {f['canonical_name'] or f['query']} "
            f"({_fights(f['fights'])}, {f['profile_path'] or 'no path'}): " + "; ".join(bits)
        )
    if not prof["flagged"]:
        lines.append("- (none)")
    lines += ["", "## Unresolved most-fought names", ""]
    for u in prof["unresolved"]:
        lines.append(f"- {u['query']} ({_fights(u['fights'])}): {u['status']}")
    if not prof["unresolved"]:
        lines.append("- (none)")
    lines += ["", "## Clean profiles", ""]
    flagged_ids = {id(f) for f in prof["flagged"]}
    for f in prof["audited"]:
        if id(f) not in flagged_ids:
            lines.append(f"- {f['canonical_name'] or f['query']} ({_fights(f['fights'])})")
    if c["profiles_clean"] == 0:
        lines.append("- (none)")
    return "\n".join(lines) + "\n"


def summarize(results: dict[str, Any]) -> str:
    """One-paragraph summary for stdout / chat."""
    c = results["counts"]
    worst = ""
    if results["profiles"]["flagged"]:
        top = results["profiles"]["flagged"][0]
        worst = (
            f" Most-flagged: {top['canonical_name'] or top['query']} "
            f"({_fights(top['fights'])}) — " + "; ".join((top["blockers"] + top["debris"])[:3])
        )
    return (
        f"Audit {results['date']}: {c['cache_rows_checked']} cached rows "
        f"checked — {c['cache_checker_failed']} checker failures, "
        f"{c['cache_stale']} stale, {c['cache_rejudged']} re-judged with "
        f"{c['cache_disagreements']} disagreements "
        f"({c['cache_rejudge_errors']} re-judge errors); "
        f"{c['profiles_audited']} most-fought profiles audited — "
        f"{c['profiles_clean']} clean, {c['profiles_flagged']} flagged, "
        f"{c['profiles_unresolved']} unresolved."
        f"{worst} Full report: "
        f"data/audit_reports/{results['date']}.md"
    )


def write_report(results: dict[str, Any], out_dir: Path) -> Path:
    """Write the dated markdown report; returns its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{results['date']}.md"
    path.write_text(format_report(results), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--sample-cap", type=int, default=25)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--skip-rejudge", action="store_true")
    parser.add_argument("--date", default=None)
    args = parser.parse_args(argv)
    root = args.repo_root or repo_root()
    out_dir = args.out_dir or (root / DEFAULT_REPORT_DIR)
    try:
        results = asyncio.run(
            run_audit(
                root=root,
                sample_cap=args.sample_cap,
                top_n=args.top_n,
                rejudge=not args.skip_rejudge,
                report_date=args.date,
            )
        )
    except Exception as exc:
        print(f"audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    path = write_report(results, out_dir)
    print(summarize(results))
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
