#!/bin/bash
# Frag-10 tier root-cause probe (live fetch, read-only).
OUT=/app/data/frag10_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  python data/frag10_20261025/frag10_tier_probe.py > "$OUT/probe.log" 2>&1
  echo "probe_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_probe.txt" 2>&1
