#!/usr/bin/env bash
set -u

cd "/mnt/d/Projects/trae_projects/AI nerd fight decision bot discord" || exit 1
source .venv/bin/activate

export DATABASE_URL="postgresql://battlebot:change_me@127.0.0.1:55432/battlebot"
export DBURL="$DATABASE_URL"
export PYTHONPATH=src

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="logs/overnight/queue_worker_${STAMP}.log"

echo "log: $LOG"

for i in $(seq 1 40); do
  echo
  echo "=== LOOP $i $(date) ==="

  .venv/bin/python -m battlebot.review.queue_worker \
    --database-url "$DATABASE_URL" \
    --worker-id "overnight-${STAMP}-${i}" \
    --limit 10 \
    --import-every 1 \
    --source-timeout-seconds 16 \
    --sleep-seconds 2 \
    --max-source-candidates 8 \
    --debug-dir data/repair_debug \
    --json

  echo "--- DB COUNT ---"
  docker compose exec -T postgres psql -U battlebot -d battlebot -c "select count(*) as imported_characters from characters;"

  echo "--- QUEUE STATUS ---"
  docker compose exec -T postgres psql -U battlebot -d battlebot -c "select status,count(*) from profile_jobs group by status order by status;"

  echo "--- FILE COUNTS ---"
  find profiles/generated -name "*.yaml" | wc -l
  find profiles/needs_review -name "*.yaml" | wc -l
  find profiles/quarantined/variant_franchise_mismatch -name "*.yaml" | wc -l

  echo "--- VARIANT SANITY ---"
  .venv/bin/python -m pytest tests/test_variant_franchise_sanity.py -q || exit 20

  sleep 60
done
