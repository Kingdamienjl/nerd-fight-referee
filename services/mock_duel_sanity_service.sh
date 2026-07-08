#!/usr/bin/env bash
set -u

cd "/mnt/d/Projects/trae_projects/AI nerd fight decision bot discord" || exit 1
source .venv/bin/activate

mkdir -p logs/sanity data/reports/sanity harvest/debug

INTERVAL_SECONDS="${SANITY_INTERVAL_SECONDS:-1800}"
SAMPLE_SIZE="${SANITY_SAMPLE_SIZE:-100}"

while true; do
  STAMP="$(date +%Y%m%d_%H%M%S)"
  LOG="logs/sanity/mock_duel_sanity_$STAMP.log"

  {
    echo "============================================================"
    echo " MOCK DUEL SANITY RUN — $STAMP"
    echo "============================================================"

    echo ""
    echo "1. Running focused tests"
    pytest -q tests/test_decision_formatter.py tests/test_fight_output_audit.py tests/test_smoke_judge.py
    TEST_CODE=$?

    if [ "$TEST_CODE" -ne 0 ]; then
      echo "Tests failed. Skipping audit."
      exit 0
    fi

    echo ""
    echo "2. Running mock duel audit"
    python -m battlebot.review.fight_output_audit \
      --sample-size "$SAMPLE_SIZE" \
      --seed "$(date +%H%M%S)" \
      --write-report

    cp -f data/reports/fight_output_audit.json "data/reports/sanity/fight_output_audit_$STAMP.json"

    echo ""
    echo "3. Harvesting social/promo candidates"
    ./harvest_promos.sh || true

    echo ""
    echo "4. Writing sanity summary"
    python - <<'PY'
from pathlib import Path
import json
import csv
from collections import Counter
from datetime import datetime

audit_path = Path("data/reports/fight_output_audit.json")
fail_path = Path("harvest/duel_failures.csv")
out = Path("logs/sanity/latest_sanity_status.md")

lines = ["# Mock Duel Sanity Status", ""]
lines.append(f"- Time: {datetime.now().isoformat(timespec='seconds')}")
lines.append("")

if audit_path.exists():
    data = json.loads(audit_path.read_text(encoding="utf-8"))
    summary = data.get("summary", {})
    lines.append("## Audit")
    for key in [
        "average_quality_score",
        "matchups_audited",
        "problem_entries",
        "total_problem_score",
        "profiles_loaded",
    ]:
        lines.append(f"- {key}: {summary.get(key)}")

    lines.append("")
    lines.append("## Problem Counts")
    for k, v in sorted((summary.get("problem_counts_by_type") or {}).items()):
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## Quality Notes")
    for k, v in sorted((summary.get("quality_note_counts") or {}).items()):
        lines.append(f"- {k}: {v}")

    entries = data.get("entries") or []
    bad = [e for e in entries if e.get("problems") or e.get("quality_notes")]
    lines.append("")
    lines.append("## First 10 flagged mock duels")
    for e in bad[:10]:
        lines.append("")
        lines.append(f"### {e.get('fighter_a')} VS {e.get('fighter_b')}")
        lines.append(f"- winner: {e.get('winner')}")
        lines.append(f"- quality_score: {e.get('quality_score')}")
        lines.append(f"- problem_score: {e.get('problem_score')}")
        lines.append(f"- problems: {', '.join(e.get('problems') or []) or 'none'}")
        lines.append(f"- quality_notes: {', '.join(e.get('quality_notes') or []) or 'none'}")

if fail_path.exists():
    counts = Counter()
    with fail_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for issue in str(row.get("Issues") or "").split(";"):
                issue = issue.strip()
                if issue:
                    counts[issue] += 1

    lines.append("")
    lines.append("## Harvest Failure Reasons")
    for k, v in counts.most_common():
        lines.append(f"- {k}: {v}")

out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(out.read_text())
PY

  } 2>&1 | tee "$LOG"

  echo "$LOG" > logs/sanity/latest_log_path.txt

  echo ""
  echo "Sleeping $INTERVAL_SECONDS seconds..."
  sleep "$INTERVAL_SECONDS"
done
