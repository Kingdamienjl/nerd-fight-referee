#!/bin/bash
# Frag2 Part 3 (re-gate 50f) backup: profiles tar + DB dump + progress/cohort snapshots.
B=/opt/referee/backups/20261022-frag2gate
mkdir -p "$B"
date -u +"start=%Y-%m-%dT%H:%M:%SZ" > "$B/status.txt"
docker exec referee-postgres-1 psql -U battlebot -d battlebot -tAc \
  "select count(*) from character_profiles" > "$B/battle_eligible_before.txt" 2> "$B/psql.err"
echo "psql_exit=$?" >> "$B/status.txt"
tar czf "$B/profiles.tar.gz" -C /opt/referee profiles 2> "$B/tar.err"
echo "tar_exit=$?" >> "$B/status.txt"
docker exec referee-postgres-1 pg_dump -U battlebot battlebot | gzip > "$B/db.sql.gz"
echo "dump_exit=$?" >> "$B/status.txt"
cp /opt/referee/data/recovery_progress.json "$B/recovery_progress.before.json" 2>/dev/null
cp /opt/referee/data/recovery_cohort.json "$B/recovery_cohort.before.json" 2>/dev/null
ls -la "$B" >> "$B/status.txt"
date -u +"end=%Y-%m-%dT%H:%M:%SZ" >> "$B/status.txt"
echo DONE >> "$B/status.txt"
