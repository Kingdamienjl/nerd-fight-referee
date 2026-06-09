#!/usr/bin/env bash
set -euo pipefail

python -m battlebot.harvest.auto_profile_harvester \
  --input profiles/rosters/backfill_roster_001.csv \
  --output profiles/generated \
  --needs-review profiles/needs_review \
  --cache-dir data/cache \
  --loop \
  --queue-mode \
  --quiet-skips \
  --skip-needs-review-existing \
  --state-file data/harvest_state.json \
  --idle-sleep 180 \
  --max-per-cycle 25
