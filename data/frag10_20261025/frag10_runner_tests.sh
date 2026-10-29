#!/bin/bash
cd /app || exit 1
OUT=/app/data/frag10_20261025
mkdir -p "$OUT"
date -u +"%Y-%m-%dT%H:%M:%SZ start" > "$OUT/status_tests.txt"
python -m py_compile src/battlebot/review/auto_repair.py src/battlebot/harvest/auto_profile_harvester.py src/battlebot/harvest/fallback_parsers.py && echo "pycompile=OK" >> "$OUT/status_tests.txt"
python -m unittest tests.test_recovery_guard tests.test_harvester_extraction -v > "$OUT/guard.log" 2>&1
echo "guard_exit=$?" >> "$OUT/status_tests.txt"
python -m unittest discover -s tests > "$OUT/discover.log" 2>&1
echo "discover_exit=$?" >> "$OUT/status_tests.txt"
tail -4 "$OUT/guard.log" >> "$OUT/status_tests.txt"
grep -E "^Ran|^OK|^FAILED" "$OUT/discover.log" >> "$OUT/status_tests.txt"
grep -c "^FAIL:" "$OUT/discover.log" >> "$OUT/status_tests.txt" || true
grep -c "^ERROR:" "$OUT/discover.log" >> "$OUT/status_tests.txt" || true
date -u +"%Y-%m-%dT%H:%M:%SZ end" >> "$OUT/status_tests.txt"
echo DONE >> "$OUT/status_tests.txt"
