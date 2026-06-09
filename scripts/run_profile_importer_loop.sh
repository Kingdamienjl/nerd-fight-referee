#!/usr/bin/env bash
set -euo pipefail

while true; do
  docker compose run --rm profile-importer \
    python -m battlebot.ingest.import_profiles profiles/generated \
      --changed-only \
      --import-state-file data/import_state.json
  sleep "${IMPORT_IDLE_SLEEP:-180}"
done
