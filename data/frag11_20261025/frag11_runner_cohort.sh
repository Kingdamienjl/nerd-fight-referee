#!/bin/bash
# Frag-11 FULL COHORT: entire remaining todo, parser-only pinned.
# Resumable via progress keys; detached + polled.
OUT=/app/data/frag11_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  HARVEST_LLM_FALLBACK=0 python data/recovery_run.py > "$OUT/cohort11.log" 2>&1
  echo "run_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_cohort.txt" 2>&1
