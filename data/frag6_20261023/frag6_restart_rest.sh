#!/bin/bash
# Frag-6: finish restarting workers 6-9 (4 and 5 already restarted),
# then verify all six are up and claiming, and log the result.
OUT=/app/data/frag6_20261023
{
  echo "start=$(date -u +%FT%TZ)"
  for w in 6 7 8 9; do
    docker restart referee-worker-$w >/dev/null 2>&1 && echo "restarted-$w $(date -u +%T)"
  done
  sleep 15
  docker ps --format '{{.Names}} {{.Status}}' | grep -E 'worker' 
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_workers.txt" 2>&1
