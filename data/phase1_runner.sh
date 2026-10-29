#!/bin/bash
# Phase 1 seed-guard fix: guard suite + queue tests + full discover.
cd /app || exit 1
OUT=/app/data/phase1_20261025
mkdir -p "$OUT"
date -u +"%Y-%m-%dT%H:%M:%SZ start" > "$OUT/status_tests.txt"
python -m py_compile src/battlebot/review/queue_seed.py tests/test_profile_queue.py && echo "pycompile=OK" >> "$OUT/status_tests.txt"
python -m unittest tests.test_recovery_guard tests.test_harvester_extraction -v > "$OUT/guard.log" 2>&1
echo "guard_exit=$?" >> "$OUT/status_tests.txt"
python -m unittest tests.test_profile_queue -v > "$OUT/queue_tests.log" 2>&1
echo "queue_exit=$?" >> "$OUT/status_tests.txt"
python -m unittest discover -s tests > "$OUT/discover.log" 2>&1
echo "discover_exit=$?" >> "$OUT/status_tests.txt"
tail -4 "$OUT/guard.log" >> "$OUT/status_tests.txt"
grep -E "^Ran|^OK|^FAILED" "$OUT/queue_tests.log" >> "$OUT/status_tests.txt"
grep -E "^Ran|^OK|^FAILED" "$OUT/discover.log" >> "$OUT/status_tests.txt"
grep -c "^FAIL:" "$OUT/discover.log" >> "$OUT/status_tests.txt" || true
grep -c "^ERROR:" "$OUT/discover.log" >> "$OUT/status_tests.txt" || true
date -u +"%Y-%m-%dT%H:%M:%SZ end" >> "$OUT/status_tests.txt"
echo DONE >> "$OUT/status_tests.txt"
