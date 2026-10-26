#!/bin/bash
# Part 1 design probe #2 (read-only + dry-runs only). Inside referee-harvester-1.
OUT=/app/data/expand_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  python data/expand_20261025/expand_design4.py > "$OUT/design_part4.log" 2>&1
  echo "design4_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_design4.txt" 2>&1
