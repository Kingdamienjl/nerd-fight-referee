#!/usr/bin/env bash
set -u
cd "/mnt/d/Projects/trae_projects/AI nerd fight decision bot discord" || exit 1
source .venv/bin/activate

mkdir -p logs/refinement logs/promote logs/autopilot data/reports harvest/debug

INTERVAL_SECONDS="${REFINEMENT_INTERVAL_SECONDS:-1200}"
MAX_PROFILES="${REFINEMENT_MAX_PROFILES:-100}"
SAMPLE_SIZE="${REFINEMENT_SAMPLE_SIZE:-100}"

while true; do
  STAMP="$(date +%Y%m%d_%H%M%S)"
  LOG="logs/refinement/refinement_$STAMP.log"
  echo "$LOG" > logs/refinement/latest_log_path.txt

  {
    echo "REFINEMENT LOOP $STAMP"
    echo "Generated: $(find profiles/generated -type f 2>/dev/null | wc -l)"
    echo "Needs review: $(find profiles/needs_review -type f 2>/dev/null | wc -l)"
    echo "Promo candidates: $(find harvest/promo_candidates -type f 2>/dev/null | wc -l)"

    echo "Running tests..."
    pytest -q tests/test_decision_formatter.py tests/test_fight_output_audit.py tests/test_smoke_judge.py

    echo "Promoting..."
    python -m battlebot.review.batch_promote profiles/needs_review --max-profiles "$MAX_PROFILES" --providers vsbattles,character_stats_profiles,superherodb,kaggle_superherodb --debug-dir data/repair_debug --json | tee "logs/promote/refinement_promote_${STAMP}.json" || true

    echo "Auditing..."
    python -m battlebot.review.fight_output_audit --sample-size "$SAMPLE_SIZE" --seed "$(date +%H%M%S)" --write-report || true

    cp -f data/reports/fight_output_audit.json "data/reports/fight_output_audit_refinement_${STAMP}.json" 2>/dev/null || true

    echo "Harvesting..."
    ./harvest_promos.sh || true

    echo "Blockers..."
    ./referee_blockers.sh | tee logs/autopilot/blockers_latest.md || true

    echo "Writing status..."
    echo "# AI Nerd Referee Refinement Status" > logs/refinement/latest_status.md
    echo "- Time: $(date --iso-8601=seconds)" >> logs/refinement/latest_status.md
    echo "- Generated profiles: $(find profiles/generated -type f 2>/dev/null | wc -l)" >> logs/refinement/latest_status.md
    echo "- Needs review profiles: $(find profiles/needs_review -type f 2>/dev/null | wc -l)" >> logs/refinement/latest_status.md
    echo "- Promo candidates: $(find harvest/promo_candidates -type f 2>/dev/null | wc -l)" >> logs/refinement/latest_status.md

    cat logs/refinement/latest_status.md
  } 2>&1 | tee "$LOG"

  echo "$LOG" > logs/refinement/latest_log_path.txt
  sleep "$INTERVAL_SECONDS"
done
