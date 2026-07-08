#!/usr/bin/env bash
set -u

cd "/mnt/d/Projects/trae_projects/AI nerd fight decision bot discord" || exit 1
source .venv/bin/activate

LOG_DIR="logs/referee_ops"
SNAP_ROOT="$LOG_DIR/candidate_snapshots"
mkdir -p "$LOG_DIR" "$SNAP_ROOT"

echo "AI Nerd Referee nonstop ops started at $(date -Is)" | tee -a "$LOG_DIR/live.log"

while true; do
  STAMP="$(date +%Y%m%d_%H%M%S)"
  LOG="$LOG_DIR/run_$STAMP.log"

  {
    echo "============================================================"
    echo "RUN $STAMP"
    echo "Time: $(date -Is)"
    echo

    echo "[status before]"
    echo "Generated profiles: $(find profiles/generated -type f 2>/dev/null | wc -l)"
    echo "Needs review: $(find profiles/needs_review -type f -not -name '.gitkeep' 2>/dev/null | wc -l)"
    echo "Promo candidates: $(find harvest/promo_candidates -type f 2>/dev/null | wc -l)"
    echo

    echo "[1/6] Fast formatter smoke tests, non-blocking..."
    pytest -q tests/test_smoke_judge.py tests/test_fight_output_audit.py tests/test_source_registry.py || true
    echo

    echo "[2/6] Audit + harvest..."
    timeout 240 bash services/referee_audit_harvest_loop.sh || true
    python services/sanitize_proactive_text_assets.py || true
    python services/sanitize_proactive_text_assets.py || true
    echo

    echo "[2.5/6] Sync franchise hints and run pre-flight checks..."
    python services/sync_proactive_franchise_hints.py || true
    python services/proactive_post_preflight.py || true
    python services/harvest_to_promotion_outbox.py || true
    python services/outbox_to_profile_refresh_queue.py || true
    python services/queue_weak_generated_profiles.py || true
    python services/mock_duel_quality_gate.py 25 || true
    python services/mock_bad_to_refresh_queue.py || true
    echo

    echo "[3/6] Promote valid needs_review profiles..."
    python services/bootstrap_promote_needs_review.py --apply --include-composite || true
    echo

    echo "[4/6] Try local refinement/promote scripts if present..."
    for script in \
      services/refinement_promote_loop.sh \
      services/refine_promote_loop.sh \
      services/referee_refinement_loop.sh \
      services/refine_needs_review.py \
      services/refinement_promote.py
    do
      if [ -f "$script" ]; then
        echo "Running $script"
        case "$script" in
          *.py) timeout 180 python "$script" || true ;;
          *.sh) timeout 180 bash "$script" || true ;;
        esac
      fi
    done
    echo

    echo "[5/6] Snapshot promo candidate pool..."
    SNAP_DIR="$SNAP_ROOT/$STAMP"
    mkdir -p "$SNAP_DIR"
    if [ -d harvest/promo_candidates ]; then
      cp -a harvest/promo_candidates/. "$SNAP_DIR/" 2>/dev/null || true
    fi
    echo "Candidate snapshot: $SNAP_DIR"
    echo "Snapshot files: $(find "$SNAP_DIR" -type f 2>/dev/null | wc -l)"
    echo

    echo "[6/6] Status after..."
    GEN_COUNT="$(find profiles/generated -type f 2>/dev/null | wc -l)"
    REVIEW_COUNT="$(find profiles/needs_review -type f -not -name '.gitkeep' 2>/dev/null | wc -l)"
    CAND_COUNT="$(find harvest/promo_candidates -type f 2>/dev/null | wc -l)"
    SNAP_COUNT="$(find "$SNAP_ROOT" -type f 2>/dev/null | wc -l)"

    echo "Generated profiles: $GEN_COUNT"
    echo "Needs review: $REVIEW_COUNT"
    echo "Promo candidates: $CAND_COUNT"
    echo "Snapshot total files: $SNAP_COUNT"
    echo

    echo "Latest promote logs:"
    ls -lt logs/promote 2>/dev/null | head -n 15 || true
    echo

    {
      echo "Last run: $STAMP"
      echo "Generated: $GEN_COUNT"
      echo "Needs review: $REVIEW_COUNT"
      echo "Promo candidates: $CAND_COUNT"
      echo "Candidate snapshot files: $SNAP_COUNT"
      echo "Last log: $LOG"
      echo "Updated: $(date -Is)"
    } > "$LOG_DIR/status.txt"

    echo "Completed: $(date -Is)"
  } 2>&1 | tee "$LOG" | tee -a "$LOG_DIR/live.log"

  sleep 300
done
