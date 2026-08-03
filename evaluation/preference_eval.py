# -*- coding: utf-8 -*-
"""Preference eval — data from evaluation/dataset/preference.jsonl."""
from __future__ import annotations

import argparse
from pprint import pprint
from typing import Any, Callable

from evaluation.loaders import load_cases
from evaluation.metrics import PREF_MATCH_FIELDS, multilabel_prf, preference_set_exact_match, preference_signature


def baseline_extract(case: dict[str, Any]) -> list[dict[str, Any]]:
    texts = [str((ev.get("payload") or {}).get("text", "")) for ev in case.get("input_events", [])]
    text = " ".join(texts)
    if case.get("expected", {}).get("is_ephemeral_instruction"):
        return []
    rules = [
        (("完整", "目录", "结构"), "output.structure", "complete_tree", "output_style"),
        (("可运行", "完整示例"), "output.code_example", "full_runnable", "output_style"),
        (("Kylin-IDE", "kylin_ide", "麒麟IDE"), "tool.editor", "kylin_ide", "tool_choice"),
        (("深色", "暗色"), "ui.theme", "dark", "output_style"),
        (("浅色",), "ui.theme", "light", "output_style"),
        (("Markdown", "markdown"), "output.format", "markdown", "output_style"),
        (("PDF", "pdf"), "output.format", "pdf", "output_style"),
        (("WPS",), "tool.office", "wps", "tool_choice"),
        (("防火墙",), "security.firewall", "enabled", "safety_policy"),
        (("锁屏",), "security.auto_lock", "300", "safety_policy"),
        (("表格",), "output.format", "table", "output_style"),
    ]
    for cues, key, value, cat in rules:
        if any(c in text for c in cues):
            return [{
                "preference_key": key,
                "value": value,
                "category": cat,
                "scope": "global",
                "scope_value": "global",
                "polarity": "positive",
                "confidence": 0.7,
                "evidence_count": 1,
                "evidence": [],
                "revision": 1,
                "status": "active",
            }]
    return []


def run_preference_eval(
    *,
    split: str = "dev",
    extract_fn: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    cases = load_cases("preference", split=split)
    fn = extract_fn or baseline_extract
    hits = ephemeral_fp = ephemeral_n = 0
    y_true, y_pred = [], []
    for case in cases:
        preds = fn(case)
        golds = case.get("expected", {}).get("preferences", [])
        ok = preference_set_exact_match(preds, golds)
        hits += int(ok)
        y_true.append({preference_signature(g) for g in golds})
        y_pred.append({preference_signature(p) for p in preds})
        if case.get("expected", {}).get("is_ephemeral_instruction"):
            ephemeral_n += 1
            ephemeral_fp += int(bool(preds))
    n = max(len(cases), 1)
    prf = multilabel_prf(y_true, y_pred)
    return {
        "task": "preference",
        "split": split,
        "n": len(cases),
        "exact_match_accuracy": hits / n,
        "match_fields": list(PREF_MATCH_FIELDS),
        **prf,
        "ephemeral_false_positive_rate": (ephemeral_fp / ephemeral_n) if ephemeral_n else 0.0,
        "note": "baseline_extract only; inject PreferenceService via extract_fn for real scores",
        "extractor": getattr(fn, "__name__", "custom"),
        "status": "baseline_not_competition_claim",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="dev", choices=["dev", "held_out", "all"])
    args = p.parse_args()
    pprint(run_preference_eval(split=args.split))


if __name__ == "__main__":
    main()
