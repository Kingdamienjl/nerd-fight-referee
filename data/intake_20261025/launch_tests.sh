#!/bin/bash
# Intake test run: guard + full discover in a one-off container (frag-6 pattern).
# Writes /app/data/intake_20261025/{guard,discover}.log + status_tests.txt.
cd /opt/referee || exit 1
mkdir -p data/intake_20261025
DBURL=$(docker inspect referee-harvester-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^DATABASE_URL=' | cut -d= -f2-)
nohup docker run --rm --network referee_default \
  -v /opt/referee/src:/app/src:rw \
  -v /opt/referee/tests:/app/tests:ro \
  -v /opt/referee/profiles:/app/profiles:rw \
  -v /opt/referee/data:/app/data:rw \
  -v /opt/referee/config:/app/config:ro \
  -e PYTHONPATH=/app/src:/app \
  -e "DATABASE_URL=$DBURL" \
  -e REDIS_URL=redis://redis:6379/0 \
  -e HARVEST_LLM_FALLBACK=0 \
  referee-harvest-guard:20260913 bash -c 'cd /app && python -m unittest tests.test_recovery_guard tests.test_harvester_extraction tests.test_category_enumerate tests.test_roster_expand > /app/data/intake_20261025/guard.log 2>&1; echo guard_exit=$? > /app/data/intake_20261025/status_tests.txt; python -m unittest discover -s tests > /app/data/intake_20261025/discover.log 2>&1; echo discover_exit=$? >> /app/data/intake_20261025/status_tests.txt; grep -E "^Ran|^OK|^FAILED" /app/data/intake_20261025/guard.log >> /app/data/intake_20261025/status_tests.txt; grep -E "^Ran|^OK|^FAILED" /app/data/intake_20261025/discover.log >> /app/data/intake_20261025/status_tests.txt; grep -c "^FAIL:" /app/data/intake_20261025/discover.log >> /app/data/intake_20261025/status_tests.txt || true; grep -c "^ERROR:" /app/data/intake_20261025/discover.log >> /app/data/intake_20261025/status_tests.txt || true; echo DONE >> /app/data/intake_20261025/status_tests.txt' > /opt/referee/data/intake_20261025/nohup_tests.out 2>&1 &
echo "launched pid $!"
