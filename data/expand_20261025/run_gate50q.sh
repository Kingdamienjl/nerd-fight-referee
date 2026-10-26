#!/bin/bash
# Expand gate 50q: EXACTLY 50 unprocessed profiles from the expanded
# population (reset todo), parser-only pinned. Inside referee-harvester-1.
OUT=/app/data/expand_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  export HARVEST_LLM_FALLBACK=0
  python data/recovery_run.py --sample 50 > "$OUT/gate50q.log" 2>&1
  echo "gate50q_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_gate50q.txt" 2>&1
