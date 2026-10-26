#!/bin/bash
# Part 1 design probe (read-only). Runs inside referee-harvester-1.
OUT=/app/data/expand_20261025
{
  echo "start=$(date -u +%FT%TZ)"
  cd /app || exit 1
  python data/expand_20261025/expand_design.py > "$OUT/design_part1.log" 2>&1
  echo "design_exit=$?"
  echo "end=$(date -u +%FT%TZ)"
  echo DONE
} >> "$OUT/status_design.txt" 2>&1
