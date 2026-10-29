#!/bin/bash
# Frag-11 dry-run proof driver: synthetic recovery dry-runs for the 3
# gate-50n profiles + the 3 promotion re-check profiles.
OUT=/app/data/frag11_20261025
export HARVEST_LLM_FALLBACK=0
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  for name in isaac.yaml oryx.yaml maliketh.yaml rodimus-prime.yaml soundwave.yaml shanoa.yaml; do
    timeout 300 python data/frag11_20261025/frag11_dryrun.py "$name" > "$OUT/dryrun_$name.log" 2>&1
    echo "$name exit=$? $(date -u +%T)"
  done
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_dryrun.txt" 2>&1
