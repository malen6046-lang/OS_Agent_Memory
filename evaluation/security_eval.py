# -*- coding: utf-8 -*-
"""Security eval — data from evaluation/dataset/security.jsonl."""
from __future__ import annotations

import argparse
import re
from pprint import pprint
from typing import Any, Callable

from evaluation.loaders import load_cases

# Patterns live here as baseline only; production SafetyService should be injected.
_PATTERNS = [
    ("password", re.compile(r"(密码|password)\s*[是:=]?", re.I)),
    ("token", re.compile(r"(token|sk-|令牌)", re.I)),
    ("id_card", re.compile(r"\d{17}[\dXx]|身份证")),
    ("bank_card", re.compile(r"\d{16,19}|银行卡")),
    ("phone", re.compile(r"1[3-9]\d{9}|手机号")),
    ("private_key", re.compile(r"BEGIN|私钥|SSH私钥", re.I)),
    ("address", re.compile(r"(地址|路|区).{2,}")),
]


def baseline_detect(text: str) -> dict[str, Any]:
    for etype, pat in _PATTERNS:
        if pat.search(text):
            if etype == "address" and "记住我喜欢" in text:
                continue
            return {
                "blocked_or_masked": True,
                "entity_type": etype,
                "error_code": "SENSITIVE_CONTENT_BLOCKED",
            }
    return {"blocked_or_masked": False, "entity_type": None, "error_code": None}


def run_security_eval(
    *,
    split: str = "dev",
    detect_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cases = load_cases("security", split=split)
    fn = detect_fn or baseline_detect
    block_hits = entity_hits = 0
    for case in cases:
        pred = fn(case["input_text"])
        exp = case["expected"]
        block_ok = pred.get("blocked_or_masked") == exp.get("blocked_or_masked")
        if exp.get("blocked_or_masked"):
            block_ok = block_ok and pred.get("error_code") == exp.get("error_code")
        entity_ok = pred.get("entity_type") == exp.get("entity_type")
        block_hits += int(block_ok)
        entity_hits += int(block_ok and entity_ok)
    n = max(len(cases), 1)
    return {
        "task": "security",
        "split": split,
        "n": len(cases),
        "block_accuracy": block_hits / n,
        "entity_type_accuracy": entity_hits / n,
        "joint_accuracy": entity_hits / n,
        "detector": getattr(fn, "__name__", "custom"),
        "status": "baseline_not_competition_claim",
        "note": "baseline regex co-located — do not claim production readiness; hard-suite expanded in P3",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="dev", choices=["dev", "held_out", "all"])
    args = p.parse_args()
    pprint(run_security_eval(split=args.split))


if __name__ == "__main__":
    main()
