#!/bin/bash
# Frag-10 dry-run proof driver: synthetic recovery dry-runs for the 13
# gate-50m profiles. Parser-only: the LLM fallback is dead (all
# upstreams down) and must never be consulted.
OUT=/app/data/frag10_20261025
export HARVEST_LLM_FALLBACK=0
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  for name in casey-jones.yaml leatherhead.yaml shredder.yaml blackarachnia.yaml devastator.yaml ironhide.yaml rodimus-prime.yaml soundwave.yaml starscream.yaml ultra-magnus.yaml arcee.yaml galvatron.yaml predaking.yaml; do
    python data/frag10_20261025/frag10_dryrun.py "$name" > "$OUT/dryrun_$name.log" 2>&1
    echo "$name exit=$? $(date -u +%T)"
  done
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_dryrun.txt" 2>&1
