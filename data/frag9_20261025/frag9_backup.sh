#!/bin/bash
# Frag-7 backup (label in $1): free-space guard + counts + profiles tar + DB dump.
LABEL=${1:-frag5}
B=/opt/referee/backups/20261025-$LABEL
mkdir -p "$B"
date -u +"start=%Y-%m-%dT%H:%M:%SZ" > "$B/status.txt"
FREE_BEFORE=$(df -m / | tail -1 | awk '{print $4}')
echo "free_mb_before=$FREE_BEFORE" >> "$B/status.txt"
docker exec referee-postgres-1 psql -U battlebot -d battlebot -tAc \
  "select count(*) from character_profiles" > "$B/battle_eligible_before.txt" 2> "$B/psql.err"
echo "psql_exit=$?" >> "$B/status.txt"
tar czf "$B/profiles.tar.gz" -C /opt/referee profiles 2> "$B/tar.err"
echo "tar_exit=$?" >> "$B/status.txt"
docker exec referee-postgres-1 pg_dump -U battlebot battlebot | gzip > "$B/db.sql.gz"
echo "dump_exit=$?" >> "$B/status.txt"
gzip -t "$B/profiles.tar.gz" && echo "profiles_tar_gzip_ok" >> "$B/status.txt"
gzip -t "$B/db.sql.gz" && echo "db_gzip_ok" >> "$B/status.txt"
cp /opt/referee/data/recovery_progress.json "$B/recovery_progress.before.json" 2>/dev/null
cp /opt/referee/data/recovery_cohort.json "$B/recovery_cohort.before.json" 2>/dev/null
FREE_AFTER=$(df -m / | tail -1 | awk '{print $4}')
echo "free_mb_after=$FREE_AFTER" >> "$B/status.txt"
ls -la "$B" >> "$B/status.txt"
date -u +"end=%Y-%m-%dT%H:%M:%SZ" >> "$B/status.txt"
echo DONE >> "$B/status.txt"
