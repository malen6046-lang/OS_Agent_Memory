"""Make the Streamlit frontend package importable in tests."""

import sys
from pathlib import Path


FRONTEND_ROOT = Path(__file__).resolve().parents[1]
if str(FRONTEND_ROOT) not in sys.path:
    sys.path.insert(0, str(FRONTEND_ROOT))
