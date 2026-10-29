#!/bin/bash
cd /app || exit 1
python3 /app/data/phase4_tally.py > /app/data/phase4_20261025/tally.log 2>&1
echo "tally_exit=$?" >> /app/data/phase4_20261025/tally.log
echo DONE >> /app/data/phase4_20261025/tally.log
