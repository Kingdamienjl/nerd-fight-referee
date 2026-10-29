#!/bin/bash
# Frag-8 gate run: sample 50l, parser-only pinned.
OUT=/app/data/frag8_20261024
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  HARVEST_LLM_FALLBACK=0 python data/recovery_run.py --sample 50 > "$OUT/sample50l.log" 2>&1
  echo "run_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_gate.txt" 2>&1
