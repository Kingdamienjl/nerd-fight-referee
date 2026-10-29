#!/bin/bash
# Frag-7 dry-run proof driver: synthetic recovery dry-runs for the two
# gate-50j profiles.
OUT=/app/data/frag7_20261023
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  for name in the-immortal.yaml the-immortal-image-comics.yaml; do
    python data/frag7_20261023/frag7_dryrun.py "$name" > "$OUT/dryrun_$name.log" 2>&1
    echo "$name exit=$? $(date -u +%T)"
  done
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_dryrun.txt" 2>&1
