#!/bin/bash
cd /app || exit 1
OUT=/app/data/frag6_20261023
mkdir -p "$OUT"
date -u +"start=%Y-%m-%dT%H:%M:%SZ" > "$OUT/status_tests.txt"
python -m py_compile src/battlebot/review/auto_repair.py && echo "pycompile=OK" >> "$OUT/status_tests.txt"
python -m unittest tests.test_recovery_guard -v > "$OUT/guard.log" 2>&1
echo "guard_exit=$?" >> "$OUT/status_tests.txt"
python -m unittest discover -s tests > "$OUT/discover.log" 2>&1
echo "discover_exit=$?" >> "$OUT/status_tests.txt"
tail -4 "$OUT/guard.log" >> "$OUT/status_tests.txt"
grep -E "^Ran|^OK|^FAILED" "$OUT/discover.log" >> "$OUT/status_tests.txt"
date -u +"end=%Y-%m-%dT%H:%M:%SZ" >> "$OUT/status_tests.txt"
echo DONE >> "$OUT/status_tests.txt"
