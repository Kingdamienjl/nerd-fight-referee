#!/bin/bash
# Frag-8 dry-run proof driver: synthetic recovery dry-runs for the three
# gate-50k profiles.
OUT=/app/data/frag8_20261024
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  for name in carnage-marvel-cinematic-universe.yaml darwin.yaml kraven-the-hunter-marvel-cinematic-universe.yaml; do
    python data/frag8_20261024/frag8_dryrun.py "$name" > "$OUT/dryrun_$name.log" 2>&1
    echo "$name exit=$? $(date -u +%T)"
  done
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_dryrun.txt" 2>&1
