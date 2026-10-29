#!/bin/bash
# Frag-11 calib3 (read-only corpus scan with the NEW code deployed).
OUT=/app/data/frag11_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  python data/frag11_20261025/frag11_calib3.py > "$OUT/calib3.log" 2>&1
  echo "calib3_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_calib3.txt" 2>&1
