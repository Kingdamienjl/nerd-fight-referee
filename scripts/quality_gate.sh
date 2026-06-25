#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

source .venv/bin/activate 2>/dev/null || true

echo "=== RUFF ==="
if [ -x .venv/bin/ruff ]; then
  .venv/bin/ruff check .
else
  python -m ruff check .
fi

echo
echo "=== TESTS ==="
if [ -x .venv/bin/python ]; then
  .venv/bin/python -m pytest -q
else
  python -m pytest -q
fi

echo
echo "=== DONE ==="
