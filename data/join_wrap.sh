#!/bin/bash
cd /app || exit 1
python3 /app/data/phase4_join.py > /app/data/phase4_20261025/join.log 2>&1
echo "join_exit=$?" >> /app/data/phase4_20261025/join.log
echo DONE >> /app/data/phase4_20261025/join.log
