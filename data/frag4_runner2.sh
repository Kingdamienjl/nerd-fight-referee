#!/bin/bash
cd /app || exit 1
OUT=/app/data/frag4_20261022
date -u +"start=%Y-%m-%dT%H:%M:%SZ" > "$OUT/status2.txt"
python -m py_compile src/battlebot/review/auto_repair.py src/battlebot/profiles/demotion.py && echo "pycompile=OK" >> "$OUT/status2.txt"
python -m unittest tests.test_recovery_guard tests.test_demotion_stamps -v > "$OUT/guard2.log" 2>&1
echo "guard_exit=$?" >> "$OUT/status2.txt"
python -m unittest discover -s tests > "$OUT/discover2.log" 2>&1
echo "discover_exit=$?" >> "$OUT/status2.txt"
date -u +"end=%Y-%m-%dT%H:%M:%SZ" >> "$OUT/status2.txt"
echo DONE >> "$OUT/status2.txt"
