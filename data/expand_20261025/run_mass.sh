#!/bin/bash
# Expand mass run: ENTIRE remaining expanded todo (stored cohort minus
# progress keys; no --sample, no --rebuild-cohort so the target set is
# exactly the manifest's). Parser-only pinned. Inside referee-harvester-1.
# Resumable via progress keys: if the harvester cycles mid-run, relaunch
# this same script and it continues from the next unprocessed profile.
OUT=/app/data/expand_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  export HARVEST_LLM_FALLBACK=0
  python data/recovery_run.py >> "$OUT/massrun.log" 2>&1
  echo "massrun_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_massrun.txt" 2>&1
