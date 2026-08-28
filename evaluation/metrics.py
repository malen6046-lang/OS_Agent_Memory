# -*- coding: utf-8 -*-
"""Evaluation metrics aligned with V1.2.1 §12.1 / 8_3 review fixes."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Iterable, Sequence


PREF_MATCH_FIELDS = (
    "preference_key",
    "value",
    "category",
    "scope",
    "scope_value",
    "polarity",
    "status",
)


def stable_int_id(text: str, *, bits: int = 62) -> int:
    """Deterministic positive int id (SHA-256); not Python's salted hash()."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % (2**bits - 1) + 1


def stable_embed(text: str, dim: int = 32) -> list[float]:
    """Deterministic demo embedding from SHA-256 (reproducible across processes)."""
    raw = hashlib.sha256(text.encode("utf-8")).digest()
    vals = []
    for i in range(dim):
        b = raw[i % len(raw)]
        vals.append(((b + i * 17) % 100) * 0.01)
    return vals


def preference_signature(pref: dict[str, Any]) -> tuple:
    return tuple(pref.get(k) for k in PREF_MATCH_FIELDS)


def preference_set_exact_match(
    preds: Sequence[dict[str, Any]], golds: Sequence[dict[str, Any]]
) -> bool:
    """Exact match on full preference field set (unordered)."""
    return {preference_signature(p) for p in preds} == {
        preference_signature(g) for g in golds
    }


def multilabel_prf(
    y_true: Sequence[set[Any]], y_pred: Sequence[set[Any]]
) -> dict[str, float]:
    """Micro/macro P/R/F1 over sets of labels per sample."""
    # micro
    tp = fp = fn = 0
    per_f1: list[float] = []
    for t, p in zip(y_true, y_pred):
        tp += len(t & p)
        fp += len(p - t)
        fn += len(t - p)
        if not t and not p:
            per_f1.append(1.0)
        else:
            prec = len(t & p) / len(p) if p else 0.0
            rec = len(t & p) / len(t) if t else 0.0
            per_f1.append(
                0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
            )
    micro_p = tp / (tp + fp) if tp + fp else 0.0
    micro_r = tp / (tp + fn) if tp + fn else 0.0
    micro_f1 = (
        0.0 if micro_p + micro_r == 0 else 2 * micro_p * micro_r / (micro_p + micro_r)
    )
    # macro by label
    label_stats: dict[Any, list[int]] = defaultdict(lambda: [0, 0, 0])  # tp,fp,fn
    for t, p in zip(y_true, y_pred):
        for lab in t & p:
            label_stats[lab][0] += 1
        for lab in p - t:
            label_stats[lab][1] += 1
        for lab in t - p:
            label_stats[lab][2] += 1
        for lab in t | p:
            label_stats.setdefault(lab, [0, 0, 0])
    f1s = []
    for tp_i, fp_i, fn_i in label_stats.values():
        p_i = tp_i / (tp_i + fp_i) if tp_i + fp_i else 0.0
        r_i = tp_i / (tp_i + fn_i) if tp_i + fn_i else 0.0
        f1s.append(0.0 if p_i + r_i == 0 else 2 * p_i * r_i / (p_i + r_i))
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    return {
        "micro_precision": micro_p,
        "micro_recall": micro_r,
        "micro_f1": micro_f1,
        "macro_f1": macro_f1,
        "sample_macro_f1": sum(per_f1) / len(per_f1) if per_f1 else 0.0,
    }


def recall_at_k(ranked_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> float:
    """True Recall@K = |Top-K ∩ gold| / |gold| (not Hit@K)."""
    if not gold_ids:
        return 0.0
    top = set(ranked_ids[:k])
    gold = set(gold_ids)
    return len(top & gold) / len(gold)


def hit_at_k(ranked_ids: Sequence[str], gold_ids: Sequence[str], k: int) -> float:
    if not gold_ids:
        return 0.0
    top = set(ranked_ids[:k])
    return 1.0 if any(g in top for g in gold_ids) else 0.0


def mrr(ranked_ids: Sequence[str], gold_ids: Sequence[str]) -> float:
    gold = set(gold_ids)
    for i, mid in enumerate(ranked_ids, 1):
        if mid in gold:
            return 1.0 / i
    return 0.0


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    idx = min(len(xs) - 1, max(0, int(round((p / 100.0) * (len(xs) - 1)))))
    return float(xs[idx])


def precision_recall(pred_ids: Iterable[str], gold_ids: Iterable[str]) -> tuple[float, float]:
    pred, gold = set(pred_ids), set(gold_ids)
    if not pred and not gold:
        return 1.0, 1.0
    if not pred:
        return 0.0, 0.0
    if not gold:
        return 0.0, 1.0
    tp = len(pred & gold)
    return tp / len(pred), tp / len(gold)
