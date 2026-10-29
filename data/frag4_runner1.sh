#!/bin/bash
cd /app || exit 1
OUT=/app/data/frag4_20261022
mkdir -p "$OUT"
date -u +"start=%Y-%m-%dT%H:%M:%SZ" > "$OUT/status1.txt"
python -m py_compile src/battlebot/review/auto_repair.py && echo "pycompile=OK" >> "$OUT/status1.txt"
python -m unittest tests.test_recovery_guard -v > "$OUT/guard.log" 2>&1
echo "guard_exit=$?" >> "$OUT/status1.txt"
python -m unittest discover -s tests > "$OUT/discover.log" 2>&1
echo "discover_exit=$?" >> "$OUT/status1.txt"
date -u +"end=%Y-%m-%dT%H:%M:%SZ" >> "$OUT/status1.txt"
echo DONE >> "$OUT/status1.txt"
