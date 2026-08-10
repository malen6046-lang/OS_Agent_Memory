# -*- coding: utf-8 -*-
"""Verify validation/final_test freeze against freeze_manifest.json."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset"
MANIFEST = DATASET / "freeze_manifest.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def check() -> list[str]:
    if not MANIFEST.exists():
        return [f"missing manifest: {MANIFEST}"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors: list[str] = []
    frozen_ids = manifest.get("frozen_case_ids") or {}
    hashes = manifest.get("frozen_content_sha256") or {}

    for fname, expected_by_split in frozen_ids.items():
        path = DATASET / fname
        if not path.exists():
            errors.append(f"missing file {fname}")
            continue
        rows = load_jsonl(path)
        actual: dict[str, list[str]] = {"validation": [], "final_test": []}
        frozen_lines = []
        for r in rows:
            sp = r.get("split")
            if sp == "held_out":
                errors.append(f"{fname}: legacy split held_out still present ({r.get('case_id')})")
            if sp in actual:
                actual[sp].append(r["case_id"])
                frozen_lines.append(json.dumps(r, ensure_ascii=False, sort_keys=True))
        for sp in ("validation", "final_test"):
            exp = sorted(expected_by_split.get(sp) or [])
            got = sorted(actual[sp])
            if exp != got:
                errors.append(f"{fname}: {sp} case_id set changed")
        expected_hash = hashes.get(fname)
        got_hash = sha256_text("\n".join(sorted(frozen_lines)))
        if expected_hash and expected_hash != got_hash:
            errors.append(
                f"{fname}: frozen content hash mismatch "
                f"(answers or fields of validation/final_test changed)"
            )
    return errors


def main() -> int:
    errs = check()
    if errs:
        print("FAIL: freeze check")
        for e in errs:
            print(" -", e)
        return 1
    print("OK: validation/final_test freeze intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
