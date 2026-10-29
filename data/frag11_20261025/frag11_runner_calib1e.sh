#!/bin/bash
OUT=/app/data/frag11_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  python data/frag11_20261025/frag11_calib1e.py > "$OUT/calib1e.log" 2>&1
  echo "calib1e_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_calib1e.txt" 2>&1
