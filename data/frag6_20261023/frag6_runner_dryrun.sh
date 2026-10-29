#!/bin/bash
# Frag-6 dry-run proof driver: verbatim screening sanity + the three
# synthetic recovery dry-runs, each writing its own report file.
OUT=/app/data/frag6_20261023
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  for name in superman-prime-earth.yaml starfire-dc-comics.yaml starfire-rebirth.yaml; do
    python data/frag6_20261023/frag6_dryrun.py "$name" > "$OUT/dryrun_$name.log" 2>&1
    echo "$name exit=$? $(date -u +%T)"
  done
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_dryrun.txt" 2>&1
