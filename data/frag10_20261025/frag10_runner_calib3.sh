#!/bin/bash
# Runs INSIDE the one-off test container (/app): calib3 over the corpus
# with the frag-10 auto_repair.py mounted over the frag-9 one.
cd /app || exit 1
OUT=/app/data/frag10_20261025
mkdir -p "$OUT"
date -u +"%Y-%m-%dT%H:%M:%SZ start" > "$OUT/status_calib3.txt"
python /app/data/frag10_20261025/frag10_calib3.py > "$OUT/calib3.log" 2>&1
echo "calib3_exit=$?" >> "$OUT/status_calib3.txt"
date -u +"%Y-%m-%dT%H:%M:%SZ end" >> "$OUT/status_calib3.txt"
echo DONE >> "$OUT/status_calib3.txt"
