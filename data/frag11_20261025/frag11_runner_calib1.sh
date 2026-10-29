#!/bin/bash
# Frag-11 calib1 (read-only corpus scan).
OUT=/app/data/frag11_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  python data/frag11_20261025/frag11_calib1.py > "$OUT/calib1.log" 2>&1
  echo "calib1_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_calib1.txt" 2>&1
