#!/bin/bash
# Part 1 design probe #2 (read-only + dry-runs only). Inside referee-harvester-1.
OUT=/app/data/expand_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  python data/expand_20261025/expand_design2.py > "$OUT/design_part2.log" 2>&1
  echo "design2_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_design2.txt" 2>&1
