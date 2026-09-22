#!/usr/bin/env bash
set -euo pipefail
cd /opt/referee
exec 9>/run/nerd-referee-legacy-repair.lock
flock -n 9 || exit 0
boot_id=$(cat /proc/sys/kernel/random/boot_id)
if [ -e .maintenance ]; then
    marker=$(cat .maintenance)
    case "$marker" in
        legacy-repair-cycle:*) [ "$marker" = "legacy-repair-cycle:$boot_id" ] && exit 0; rm -f .maintenance ;;
        *) exit 0 ;;
    esac
fi
output=/opt/referee/backups/legacy-repair-20260922
mkdir -p "$output"
printf 'legacy-repair-cycle:%s\n' "$boot_id" > .maintenance
cleanup() {
    docker rm -f referee-legacy-repair-job >/dev/null 2>&1 || true
    docker compose start worker harvester >/dev/null 2>&1 || true
    rm -f /opt/referee/.maintenance
}
trap cleanup EXIT
docker compose stop -t 20 worker harvester >/dev/null
run_batch() {
    docker run --rm --name referee-legacy-repair-job --network referee_default --env-file /opt/referee/.env \
        -v /opt/referee:/workspace -v /opt/referee/profiles/generated:/live/profiles/generated \
        -v "$output":/results -w /workspace -e PYTHONPATH=/workspace/src:/workspace \
        referee-operational:20260909 python -P services/repair_legacy_profiles.py \
        --root /live/profiles/generated --output /results --limit 16 "$@"
}
run_batch
run_batch --apply
