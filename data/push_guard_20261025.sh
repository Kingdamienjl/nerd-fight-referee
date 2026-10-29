#!/bin/bash
# Push-job guard re-run: compile the 3 intake files + guard suite + full discover
# in a one-off container (frag-6 / intake pattern). Writes to data/push_guard_20261025/.
cd /opt/referee || exit 1
mkdir -p data/push_guard_20261025
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
  referee-harvest-guard:20260913 bash -c 'cd /app && python -m compileall -q src/battlebot/harvest/category_enumerate.py data/franchise_intake_20261025.py tests/test_category_enumerate.py && echo COMPILE_OK > /app/data/push_guard_20261025/compile.txt || echo COMPILE_FAIL > /app/data/push_guard_20261025/compile.txt; python -m unittest tests.test_recovery_guard tests.test_harvester_extraction tests.test_category_enumerate tests.test_roster_expand > /app/data/push_guard_20261025/guard.log 2>&1; echo guard_exit=$? > /app/data/push_guard_20261025/status.txt; python -m unittest discover -s tests > /app/data/push_guard_20261025/discover.log 2>&1; echo discover_exit=$? >> /app/data/push_guard_20261025/status.txt; grep -E "^Ran|^OK|^FAILED" /app/data/push_guard_20261025/guard.log >> /app/data/push_guard_20261025/status.txt; grep -E "^Ran|^OK|^FAILED" /app/data/push_guard_20261025/discover.log >> /app/data/push_guard_20261025/status.txt; grep -c "^FAIL:" /app/data/push_guard_20261025/discover.log >> /app/data/push_guard_20261025/status.txt || true; grep -c "^ERROR:" /app/data/push_guard_20261025/discover.log >> /app/data/push_guard_20261025/status.txt || true; echo DONE >> /app/data/push_guard_20261025/status.txt' > /opt/referee/data/push_guard_20261025/nohup.out 2>&1 &
echo "launched pid $!"
