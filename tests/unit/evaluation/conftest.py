"""Ensure project ``evaluation`` package wins over this test directory name."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
UNIT_DIR = Path(__file__).resolve().parents[1]

# Drop paths that would make `import evaluation` resolve to this test folder.
for p in (str(UNIT_DIR), str(Path(__file__).resolve().parent)):
    while p in sys.path:
        sys.path.remove(p)

# Project root must be first.
while str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

# If a shadowed evaluation (this test dir) was already imported, clear it.
ev = sys.modules.get("evaluation")
if ev is not None:
    ev_file = getattr(ev, "__file__", "") or ""
    if "tests" in Path(ev_file).as_posix() or ev_file == "":
        for key in list(sys.modules):
            if key == "evaluation" or key.startswith("evaluation."):
                del sys.modules[key]
