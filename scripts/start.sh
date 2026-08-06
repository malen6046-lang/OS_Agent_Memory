#!/usr/bin/env bash
# Start the FastAPI backend with the full Algorithm V1.1 adapter graph.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST=${HOST:-127.0.0.1}
PORT=${PORT:-8000}
export OS_AGENT_ENV=${OS_AGENT_ENV:-algorithm_modules}

echo "Starting OS Agent Memory on http://${HOST}:${PORT} (profile=${OS_AGENT_ENV})"
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --workers 1
