#!/usr/bin/env bash
# One-shot setup: create venv and install runtime + test + frontend extras.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3.12}
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "CPython 3.12 is required (V1.2.1 baseline). Install it first." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test,frontend]"

echo "setup complete. Activate with: source .venv/bin/activate"
echo "Then run: ./scripts/start.sh"
