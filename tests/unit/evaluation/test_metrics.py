# -*- coding: utf-8 -*-
"""Metrics: preference exact-match/F1, multi-gold Recall@K, stable SHA-256 ids."""
from __future__ import annotations

import multiprocessing as mp

from evaluation.metrics import (
    multilabel_prf,
    preference_set_exact_match,
    recall_at_k,
    stable_embed,
    stable_int_id,
)


def _pref(**kwargs):
    base = {
        "preference_key": "tool.editor",
        "value": "kylin_ide",
        "category": "tool_choice",
        "scope": "global",
        "scope_value": "global",
        "polarity": "positive",
        "status": "active",
    }
    base.update(kwargs)
    return base


def test_preference_set_exact_match_unordered() -> None:
    a = _pref(preference_key="a", value="1")
    b = _pref(preference_key="b", value="2")
    assert preference_set_exact_match([a, b], [b, a]) is True
    assert preference_set_exact_match([a], [a, b]) is False
    assert preference_set_exact_match([], []) is True


def test_preference_exact_match_requires_all_fields() -> None:
    gold = _pref()
    pred = _pref(status="inactive")
    assert preference_set_exact_match([pred], [gold]) is False


def test_multilabel_prf_perfect_and_partial() -> None:
    y_true = [{("k", "v")}, {("a", "1"), ("b", "2")}]
    y_pred = [{("k", "v")}, {("a", "1")}]
    out = multilabel_prf(y_true, y_pred)
    assert out["micro_precision"] == 1.0
    assert abs(out["micro_recall"] - (2 / 3)) < 1e-9
    assert 0.0 < out["macro_f1"] <= 1.0
    assert 0.0 < out["sample_macro_f1"] <= 1.0


def test_recall_at_k_multi_gold_not_hit() -> None:
    """True Recall@K = |Top-K ∩ gold| / |gold| (multi-gold)."""
    ranked = ["m1", "m2", "m3", "m4", "m5"]
    gold = ["m1", "m9"]
    assert recall_at_k(ranked, gold, k=5) == 0.5  # 1/2
    assert recall_at_k(ranked, gold, k=1) == 0.5
    # Hit@K would be 1.0 at k=5; Recall stays 0.5
    gold3 = ["m1", "m2", "m9"]
    assert abs(recall_at_k(ranked, gold3, k=5) - (2 / 3)) < 1e-9


def test_recall_at_k_empty_gold() -> None:
    assert recall_at_k(["m1"], [], k=5) == 0.0


def _child_stable(q: mp.Queue, text: str) -> None:
    q.put((stable_int_id(text), stable_embed(text, 8)))


def test_stable_hash_cross_process_consistency() -> None:
    text = "银河麒麟打开终端"
    local_id = stable_int_id(text)
    local_emb = stable_embed(text, 8)
    ctx = mp.get_context("spawn")
    q: mp.Queue = ctx.Queue()
    proc = ctx.Process(target=_child_stable, args=(q, text))
    proc.start()
    remote_id, remote_emb = q.get(timeout=30)
    proc.join(timeout=30)
    assert proc.exitcode == 0
    assert remote_id == local_id
    assert remote_emb == local_emb
    # positive, deterministic
    assert local_id > 0
    assert stable_int_id(text) == local_id
