#!/bin/bash
# Fragment screen phase 1: guard suite + full discover, detached in harvester.
cd /app || exit 1
OUT=/app/data/frag_20261022
mkdir -p "$OUT"
date -u +"start=%Y-%m-%dT%H:%M:%SZ" > "$OUT/status.txt"
python -m unittest tests.test_recovery_guard -v > "$OUT/guard.log" 2>&1
echo "guard_exit=$?" >> "$OUT/status.txt"
date -u +"guard_done=%Y-%m-%dT%H:%M:%SZ" >> "$OUT/status.txt"
python -m unittest discover -s tests > "$OUT/discover.log" 2>&1
echo "discover_exit=$?" >> "$OUT/status.txt"
date -u +"end=%Y-%m-%dT%H:%M:%SZ" >> "$OUT/status.txt"
echo DONE >> "$OUT/status.txt"
