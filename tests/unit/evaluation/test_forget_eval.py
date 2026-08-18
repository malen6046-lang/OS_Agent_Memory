# -*- coding: utf-8 -*-
"""Forget eval: false-delete detection and residual checks."""
from __future__ import annotations

import pytest

from evaluation.forget_eval import (
    make_confirmation_token,
    simulate_execute,
)


def _case() -> dict:
    return {
        "case_id": "FORG-T1",
        "user_id": "usr_kylin_003",
        "instruction": "忘记防火墙设置",
        "memory_fixtures": [
            {"memory_id": "mem_fw", "user_id": "usr_kylin_003", "status": "active"},
            {"memory_id": "mem_theme", "user_id": "usr_kylin_003", "status": "active"},
        ],
        "expected_preview": {
            "should_delete_ids": ["mem_fw"],
            "should_keep_ids": ["mem_theme"],
        },
        "expected_execute": {
            "drop_collection_forbidden": True,
            "status_after": "tombstoned",
        },
    }


def test_token_derived_not_from_gold() -> None:
    case = _case()
    tok = make_confirmation_token(case)
    assert tok.startswith("tok_")
    assert len(tok) == 4 + 12
    # stable
    assert make_confirmation_token(case) == tok


def test_false_delete_ids_when_preview_hits_keep() -> None:
    case = _case()
    preview = {
        "should_delete_ids": ["mem_fw", "mem_theme"],  # wrongly deletes keep
        "should_keep_ids": [],
        "confirmation_token": make_confirmation_token(case),
        "confirmation_required": True,
    }
    exe = simulate_execute(case, preview)
    assert exe["ok"] is True
    assert "mem_theme" in exe["false_delete_ids"]
    assert exe["status_after"] == "tombstoned"
    assert exe["store_snapshot"]["mem_theme"] == "tombstoned"
    assert exe["store_snapshot"]["mem_fw"] == "tombstoned"
    # deleted ids removed from vector index → no residual for deleted set
    assert exe["residual_in_vector"] is False


def test_residual_when_token_mismatch() -> None:
    case = _case()
    preview = {
        "should_delete_ids": ["mem_fw"],
        "confirmation_token": "tok_bad",
    }
    exe = simulate_execute(case, preview)
    assert exe["ok"] is False
    assert exe["error"] == "confirmation_token_mismatch"
    assert exe["residual_in_sqlite"] is True
    assert exe["residual_in_vector"] is True


def test_drop_collection_forbidden() -> None:
    case = _case()
    preview = {
        "should_delete_ids": ["mem_fw"],
        "confirmation_token": make_confirmation_token(case),
    }
    with pytest.raises(RuntimeError, match="DropCollection"):
        simulate_execute(case, preview, drop_collection=True)


def test_clean_execute_no_false_delete() -> None:
    case = _case()
    preview = {
        "should_delete_ids": ["mem_fw"],
        "confirmation_token": make_confirmation_token(case),
    }
    exe = simulate_execute(case, preview)
    assert exe["ok"] is True
    assert exe["false_delete_ids"] == []
    assert exe["residual_in_sqlite"] is False
    assert exe["residual_in_vector"] is False
    assert exe["store_snapshot"]["mem_fw"] == "tombstoned"
    assert exe["store_snapshot"]["mem_theme"] == "active"
