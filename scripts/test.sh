#!/usr/bin/env bash
# Run the full test suite (backend + frontend).
set -euo pipefail
cd "$(dirname "$0")/.."

python -m pytest -q
echo "---- frontend ----"
python -m pytest frontend/tests -q
