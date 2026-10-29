#!/bin/bash
OUT=/app/data/frag11_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  python data/frag11_20261025/frag11_calib1c.py > "$OUT/calib1c.log" 2>&1
  echo "calib1c_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_calib1c.txt" 2>&1
