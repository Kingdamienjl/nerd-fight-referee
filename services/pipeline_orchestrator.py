#!/usr/bin/env python3
"""AI Nerd Referee Pipeline Orchestrator

Coordinates the full end-to-end automated referee lifecycle:
  1. Harvest: Expands candidates and refreshes missing fighters.
  2. Refine & Repair: Auto-resolves source choices and repairs malformed profile YAMLs.
  3. Promote: Evaluates quality and graduates validated fighters to profiles/generated/.
  4. Mock Duels: Evaluates matchup simulation quality gates and triages low-quality profiles.
  5. Discord Announcer: Pushes verified fight breakdowns and matchup cards to the Discord webhook.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "pipeline_orchestrator.log"
REPORT_FILE = LOG_DIR / "pipeline_orchestrator_report.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("pipeline_orchestrator")


class GracefulKiller:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args: Any) -> None:
        logger.info("Termination signal received. Exiting loop cleanly...")
        self.kill_now = True


def run_subcommand(cmd: list[str], *, cwd: Path = ROOT, timeout: int = 600) -> dict[str, Any]:
    cmd_str = " ".join(cmd)
    logger.info(f"Running: {cmd_str}")
    start = time.time()
    env = {**os.environ, "PYTHONPATH": f"{ROOT}/src:{ROOT}"}
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        elapsed = round(time.time() - start, 2)
        success = (proc.returncode == 0)
        tail = proc.stdout[-1500:] if proc.stdout else ""
        if success:
            logger.info(f"Completed ({elapsed}s): {cmd_str}")
        else:
            logger.warning(f"Failed (code {proc.returncode}, {elapsed}s): {cmd_str}")
        return {
            "command": cmd_str,
            "success": success,
            "returncode": proc.returncode,
            "elapsed_seconds": elapsed,
            "output_tail": tail,
        }
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - start, 2)
        logger.error(f"Timeout ({timeout}s): {cmd_str}")
        return {
            "command": cmd_str,
            "success": False,
            "returncode": -1,
            "elapsed_seconds": elapsed,
            "output_tail": "Timed out",
        }
    except Exception as exc:
        elapsed = round(time.time() - start, 2)
        logger.error(f"Error running {cmd_str}: {exc}")
        return {
            "command": cmd_str,
            "success": False,
            "returncode": -2,
            "elapsed_seconds": elapsed,
            "output_tail": str(exc),
        }


def run_pipeline_iteration(*, dry_run: bool = False) -> dict[str, Any]:
    logger.info(f"=== Starting Pipeline Iteration (dry_run={dry_run}) ===")
    iteration_start = datetime.now()
    results: list[dict[str, Any]] = []

    # 1. Harvest Stage
    harvest_script = ROOT / "services" / "morning_expansion_harvest.py"
    if harvest_script.exists():
        results.append(run_subcommand([sys.executable, str(harvest_script)]))

    # 2. Refine & Repair Stage
    source_choice_script = ROOT / "services" / "auto_resolve_source_choice.py"
    if source_choice_script.exists():
        results.append(run_subcommand([sys.executable, str(source_choice_script)]))

    # 3. Promote Stage
    ranker_script = ROOT / "services" / "promotion_ranker.py"
    if ranker_script.exists():
        results.append(run_subcommand([sys.executable, str(ranker_script)]))

    promote_script = ROOT / "services" / "local_yaml_promote_safe.py"
    if promote_script.exists():
        promote_cmd = [sys.executable, str(promote_script)]
        if not dry_run:
            promote_cmd.append("--apply")
        results.append(run_subcommand(promote_cmd))

    # 4. Mock Duels & Quality Gate Stage
    quality_gate_script = ROOT / "services" / "mock_duel_quality_gate.py"
    if quality_gate_script.exists():
        results.append(run_subcommand([sys.executable, str(quality_gate_script)]))

    bad_refresh_script = ROOT / "services" / "mock_bad_to_refresh_queue.py"
    if bad_refresh_script.exists():
        results.append(run_subcommand([sys.executable, str(bad_refresh_script)]))

    # 5. Discord Webhook Announcer Stage
    announcer_script = ROOT / "services" / "proactive_referee_announcer.py"
    if announcer_script.exists():
        announcer_cmd = [sys.executable, str(announcer_script), "--mode", "auto"]
        if dry_run:
            announcer_cmd.append("--dry-run")
        results.append(run_subcommand(announcer_cmd))

    duration = round((datetime.now() - iteration_start).total_seconds(), 2)
    success_count = sum(1 for r in results if r["success"])
    total_count = len(results)

    report = {
        "timestamp": iteration_start.isoformat(),
        "duration_seconds": duration,
        "dry_run": dry_run,
        "summary": f"{success_count}/{total_count} steps succeeded",
        "steps": results,
    }

    try:
        REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning(f"Could not write report file: {exc}")

    logger.info(f"=== Pipeline Iteration Finished in {duration}s ({success_count}/{total_count} steps succeeded) ===")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Nerd Referee Pipeline Orchestrator")
    parser.add_argument("--loop", action="store_true", help="Run continuously in a loop")
    parser.add_argument("--interval", type=int, default=None, help="Interval in seconds between loops")
    parser.add_argument("--dry-run", action="store_true", help="Execute in dry-run mode without publishing or moving files")
    parser.add_argument("--once", action="store_true", help="Run once and exit immediately (default)")
    args = parser.parse_args()

    # Load interval from args or env (REFEREE_WORKER_INTERVAL)
    interval = args.interval
    if interval is None:
        try:
            interval = int(os.getenv("REFEREE_WORKER_INTERVAL", "60"))
        except ValueError:
            interval = 60

    if not args.loop:
        report = run_pipeline_iteration(dry_run=args.dry_run)
        print(json.dumps(report, indent=2))
        return 0

    logger.info(f"Starting pipeline orchestrator loop (interval={interval}s, dry_run={args.dry_run})")
    killer = GracefulKiller()
    while not killer.kill_now:
        try:
            run_pipeline_iteration(dry_run=args.dry_run)
        except Exception as exc:
            logger.error(f"Iteration raised an unexpected exception: {exc}")

        logger.info(f"Sleeping for {interval}s before next iteration...")
        sleep_start = time.time()
        while time.time() - sleep_start < interval and not killer.kill_now:
            time.sleep(1)

    logger.info("Pipeline orchestrator loop stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())