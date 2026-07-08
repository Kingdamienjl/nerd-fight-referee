#!/usr/bin/env bash
set -u

cd "/mnt/d/Projects/trae_projects/AI nerd fight decision bot discord" || exit 1
source .venv/bin/activate

LOG_DIR="logs/harvest_daemon"
mkdir -p "$LOG_DIR"

echo "AI Nerd Referee nonstop harvest/promote started at $(date -Is)" | tee -a "$LOG_DIR/daemon.log"

while true; do
  STAMP="$(date +%Y%m%d_%H%M%S)"
  LOG="$LOG_DIR/run_$STAMP.log"

  {
    echo "============================================================"
    echo "RUN $STAMP"
    echo "Time: $(date -Is)"
    echo "Generated before: $(find profiles/generated -type f | wc -l)"
    echo "Needs review before: $(find profiles/needs_review -type f -not -name '.gitkeep' | wc -l)"
    echo "Promo candidates before: $(find harvest/promo_candidates -type f 2>/dev/null | wc -l)"

    echo
    echo "[1/4] Running audit harvest loop..."
    timeout 180 bash services/referee_audit_harvest_loop.sh || true

    echo
    echo "[2/4] Promoting valid needs_review profiles..."
    python services/bootstrap_promote_needs_review.py --apply --include-composite || true

    echo
    echo "[3/4] Writing quick status..."
    echo "Generated after: $(find profiles/generated -type f | wc -l)"
    echo "Needs review after: $(find profiles/needs_review -type f -not -name '.gitkeep' | wc -l)"
    echo "Promo candidates after: $(find harvest/promo_candidates -type f 2>/dev/null | wc -l)"

    echo
    echo "[4/5] Snapshotting promo candidate pool..."
    SNAP_DIR="logs/harvest_daemon/candidate_snapshots/$STAMP"
    mkdir -p "$SNAP_DIR"
    if [ -d harvest/promo_candidates ]; then
      cp -a harvest/promo_candidates/. "$SNAP_DIR/" 2>/dev/null || true
    fi
    echo "Candidate snapshot: $SNAP_DIR"

    echo
    echo "[5/5] Latest promotion logs:"
    ls -lt logs/promote 2>/dev/null | head -n 12 || true

    echo
    echo "Completed: $(date -Is)"
  } 2>&1 | tee "$LOG"

  echo "Last run: $STAMP" > "$LOG_DIR/status.txt"
  echo "Generated: $(find profiles/generated -type f | wc -l)" >> "$LOG_DIR/status.txt"
  echo "Needs review: $(find profiles/needs_review -type f -not -name '.gitkeep' | wc -l)" >> "$LOG_DIR/status.txt"
  echo "Promo candidates: $(find harvest/promo_candidates -type f 2>/dev/null | wc -l)" >> "$LOG_DIR/status.txt"
  echo "Last log: $LOG" >> "$LOG_DIR/status.txt"

  sleep 300
done
