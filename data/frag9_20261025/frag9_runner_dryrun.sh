#!/bin/bash
# Frag-9 dry-run proof driver: synthetic recovery dry-runs for the two
# gate-50l profiles.
OUT=/app/data/frag9_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  for name in venom-earth-616.yaml venom-marvel-cinematic-universe.yaml; do
    python data/frag9_20261025/frag9_dryrun.py "$name" > "$OUT/dryrun_$name.log" 2>&1
    echo "$name exit=$? $(date -u +%T)"
  done
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_dryrun.txt" 2>&1
