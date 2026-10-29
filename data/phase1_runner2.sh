#!/bin/bash
cd /app || exit 1
OUT=/app/data/phase1_20261025
date -u +"%Y-%m-%dT%H:%M:%SZ rerun-start" > "$OUT/status_tests2.txt"
python -m unittest tests.test_recovery_guard tests.test_harvester_extraction -v > "$OUT/guard2.log" 2>&1
echo "guard_exit=$?" >> "$OUT/status_tests2.txt"
python -m unittest discover -s tests > "$OUT/discover2.log" 2>&1
echo "discover_exit=$?" >> "$OUT/status_tests2.txt"
grep -E "^Ran|^OK|^FAILED" "$OUT/guard2.log" >> "$OUT/status_tests2.txt"
grep -E "^Ran|^OK|^FAILED" "$OUT/discover2.log" >> "$OUT/status_tests2.txt"
grep -c "^FAIL:" "$OUT/discover2.log" >> "$OUT/status_tests2.txt" || true
grep -c "^ERROR:" "$OUT/discover2.log" >> "$OUT/status_tests2.txt" || true
date -u +"%Y-%m-%dT%H:%M:%SZ rerun-end" >> "$OUT/status_tests2.txt"
echo DONE >> "$OUT/status_tests2.txt"
