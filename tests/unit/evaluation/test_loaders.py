# -*- coding: utf-8 -*-
"""Loader integrity: corrupt JSONL, missing fields, duplicate IDs, split filter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.loaders import FILES, load_cases, load_jsonl, validate_rows


def test_load_jsonl_raises_on_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"ok": 1}\n{not-json\n', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_jsonl(path)


def test_validate_rows_missing_fields() -> None:
    rows = [{"case_id": "PREF-X", "user_id": "u1"}]  # missing split/expected
    errs = validate_rows("preference", rows)
    assert any("missing field 'split'" in e for e in errs)
    assert any("missing field 'expected'" in e for e in errs)


def test_validate_rows_duplicate_ids() -> None:
    base = {
        "case_id": "PREF-DUP",
        "user_id": "u1",
        "split": "dev",
        "expected": {},
    }
    errs = validate_rows("preference", [base, dict(base)])
    assert any("duplicate case_id=" in e for e in errs)


def test_validate_rows_ok_for_minimal() -> None:
    rows = [
        {
            "case_id": "SEC-1",
            "user_id": "u1",
            "split": "dev",
            "input_text": "x",
            "expected": {},
        }
    ]
    assert validate_rows("security", rows) == []


def test_shipped_datasets_parse_and_validate() -> None:
    """All V0.1 JSONL files must parse and pass field/id checks."""
    from evaluation.loaders import DATASET_DIR, ID_FIELD

    for task, fname in FILES.items():
        path = DATASET_DIR / fname
        assert path.exists(), fname
        rows = load_jsonl(path)
        assert rows, fname
        errs = validate_rows(task, rows)
        assert errs == [], f"{fname}: {errs[:5]}"
        id_key = ID_FIELD[task]
        ids = [r[id_key] for r in rows]
        assert len(ids) == len(set(ids))


def test_load_cases_split_filter() -> None:
    dev = load_cases("preference", split="dev")
    all_rows = load_cases("preference", split="all")
    assert all(r.get("split") == "dev" for r in dev)
    assert len(all_rows) >= len(dev)


def test_load_cases_unknown_task() -> None:
    with pytest.raises(KeyError):
        load_cases("not_a_task")
