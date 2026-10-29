#!/bin/bash
# Frag-11 live reproduction probe driver (read-only fetches).
OUT=/app/data/frag11_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  for name in isaac.yaml oryx.yaml maliketh.yaml; do
    timeout 240 python data/frag11_20261025/frag11_probe_live.py "$name" > "$OUT/probe_$name.log" 2>&1
    echo "$name exit=$? $(date -u +%T)"
  done
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_probe.txt" 2>&1
