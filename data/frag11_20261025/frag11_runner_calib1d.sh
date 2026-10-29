#!/bin/bash
OUT=/app/data/frag11_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  python data/frag11_20261025/frag11_calib1d.py > "$OUT/calib1d.log" 2>&1
  echo "calib1d_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_calib1d.txt" 2>&1
