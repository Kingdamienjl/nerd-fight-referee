#!/bin/bash
# Frag-11 gate run: sample 50o, parser-only pinned.
OUT=/app/data/frag11_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  HARVEST_LLM_FALLBACK=0 python data/recovery_run.py --sample 50 > "$OUT/sample50o.log" 2>&1
  echo "run_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_gate.txt" 2>&1
