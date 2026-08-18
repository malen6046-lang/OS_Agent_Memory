#!/usr/bin/env bash
# Run Dataset V0.1 evaluation and write reports under evaluation/reports/.
set -euo pipefail
cd "$(dirname "$0")/.."

SPLIT=${1:-dev}
python -m evaluation.run_all --split "$SPLIT"
echo "reports written to evaluation/reports/"
