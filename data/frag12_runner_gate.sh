#!/bin/bash
# Frag-12 gate run: sample 50p (todo is 3 profiles: leafling, netskie,
# sheary -- the rebuilt cohort's todo is exhausted; see phase3.md),
# parser-only pinned. Runs inside referee-harvester-1.
OUT=/app/data/frag12_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  HARVEST_LLM_FALLBACK=0 python data/recovery_run.py --sample 50 > "$OUT/sample50p.log" 2>&1
  echo "run_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_gate50p.txt" 2>&1
