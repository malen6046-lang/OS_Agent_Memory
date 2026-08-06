#!/usr/bin/env bash
# Pre-flight checks for the Kylin Linux Desktop V11 target machine.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== CPython 3.12 =="
python -c 'import sys; assert sys.version_info[:2] == (3, 12), "need CPython 3.12 (V1.2.1 baseline)"; print(sys.version.split()[0])'

echo "== core runtime deps =="
python - <<'PY'
import importlib.util
required = ["fastapi", "pydantic", "sqlalchemy", "uvicorn", "httpx", "numpy", "yaml", "pytest"]
for name in required:
    spec = importlib.util.find_spec(name)
    print(f"  {name}: {'OK' if spec else 'MISSING'}")
PY

echo "== optional / real-machine components =="
python - <<'PY'
import importlib.util
for name in ("sentence_transformers", "faiss", "kylin_sdk"):
    spec = importlib.util.find_spec(name)
    print(f"  {name}: {'present' if spec else 'NOT INSTALLED'}")
PY

echo "== health of current profile =="
export OS_AGENT_ENV=${OS_AGENT_ENV:-algorithm_modules}
python -c 'from fastapi.testclient import TestClient; from app.main import app; c = TestClient(app, raise_server_exceptions=False); r = c.get("/api/v1/health"); print(r.status_code, r.json().get("data", {}).get("status"))'
