#!/usr/bin/env bash
# Initialize the configured SQLite database and registered ORM tables.
set -euo pipefail
cd "$(dirname "$0")/.."

python -m scripts.init_db
