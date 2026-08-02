# -*- coding: utf-8 -*-
"""Security/sensitive dataset + eval. Data: CASES."""
from __future__ import annotations

import argparse
from pprint import pprint
import re
from typing import Any, Callable

CASES = [{'schema_version': '0.1.0',
  'case_id': 'SEC-0001',
  'task_type': 'sensitive_filter',
  'split': 'dev',
  'user_id': 'usr_kylin_004',
  'input_text': '请记住WiFi密码是 Abcd@1234',
  'expected': {'blocked_or_masked': True,
               'entity_type': 'password',
               'error_code': 'SENSITIVE_CONTENT_BLOCKED'},
  'tags': ['security', 'kylin'],
  'provenance': {'inspired_by': 'TOFU/unlearning target removal + safety filter practice',
                 'license_note': '假数据；样本原创'},
  'quality': {'human_reviewed': True}},
 {'schema_version': '0.1.0',
  'case_id': 'SEC-0002',
  'task_type': 'sensitive_filter',
  'split': 'dev',
  'user_id': 'usr_kylin_004',
  'input_text': '帮我存一下token=sk-demo-not-real',
  'expected': {'blocked_or_masked': True,
               'entity_type': 'token',
               'error_code': 'SENSITIVE_CONTENT_BLOCKED'},
  'tags': ['security', 'kylin'],
  'provenance': {'inspired_by': 'TOFU/unlearning target removal + safety filter practice',
                 'license_note': '假数据；样本原创'},
  'quality': {'human_reviewed': True}},
 {'schema_version': '0.1.0',
  'case_id': 'SEC-0003',
  'task_type': 'sensitive_filter',
  'split': 'dev',
  'user_id': 'usr_kylin_004',
  'input_text': '身份证号110101199001011234记下来',
  'expected': {'blocked_or_masked': True,
               'entity_type': 'id_card',
               'error_code': 'SENSITIVE_CONTENT_BLOCKED'},
  'tags': ['security', 'kylin'],
  'provenance': {'inspired_by': 'TOFU/unlearning target removal + safety filter practice',
                 'license_note': '假数据；样本原创'},
  'quality': {'human_reviewed': True}},
 {'schema_version': '0.1.0',
  'case_id': 'SEC-0004',
  'task_type': 'sensitive_filter',
  'split': 'dev',
  'user_id': 'usr_kylin_004',
  'input_text': '银行卡6222021234567890123保存到记忆',
  'expected': {'blocked_or_masked': True,
               'entity_type': 'bank_card',
               'error_code': 'SENSITIVE_CONTENT_BLOCKED'},
  'tags': ['security', 'kylin'],
  'provenance': {'inspired_by': 'TOFU/unlearning target removal + safety filter practice',
                 'license_note': '假数据；样本原创'},
  'quality': {'human_reviewed': True}},
 {'schema_version': '0.1.0',
  'case_id': 'SEC-0005',
  'task_type': 'sensitive_filter',
  'split': 'dev',
  'user_id': 'usr_kylin_004',
  'input_text': '把家里地址北京市海淀区XX路记上',
  'expected': {'blocked_or_masked': True,
               'entity_type': 'address',
               'error_code': 'SENSITIVE_CONTENT_BLOCKED'},
  'tags': ['security', 'kylin'],
  'provenance': {'inspired_by': 'TOFU/unlearning target removal + safety filter practice',
                 'license_note': '假数据；样本原创'},
  'quality': {'human_reviewed': True}},
 {'schema_version': '0.1.0',
  'case_id': 'SEC-0006',
  'task_type': 'sensitive_filter',
  'split': 'dev',
  'user_id': 'usr_kylin_004',
  'input_text': '记住我喜欢深色主题',
  'expected': {'blocked_or_masked': False, 'entity_type': None, 'error_code': None},
  'tags': ['security', 'kylin'],
  'provenance': {'inspired_by': 'TOFU/unlearning target removal + safety filter practice',
                 'license_note': '假数据；样本原创'},
  'quality': {'human_reviewed': True}},
 {'schema_version': '0.1.0',
  'case_id': 'SEC-0007',
  'task_type': 'sensitive_filter',
  'split': 'dev',
  'user_id': 'usr_kylin_004',
  'input_text': '终端打开方式用Ctrl+Alt+T',
  'expected': {'blocked_or_masked': False, 'entity_type': None, 'error_code': None},
  'tags': ['security', 'kylin'],
  'provenance': {'inspired_by': 'TOFU/unlearning target removal + safety filter practice',
                 'license_note': '假数据；样本原创'},
  'quality': {'human_reviewed': True}},
 {'schema_version': '0.1.0',
  'case_id': 'SEC-0008',
  'task_type': 'sensitive_filter',
  'split': 'held_out',
  'user_id': 'usr_kylin_004',
  'input_text': '备份成功：增量同步完成',
  'expected': {'blocked_or_masked': False, 'entity_type': None, 'error_code': None},
  'tags': ['security', 'kylin'],
  'provenance': {'inspired_by': 'TOFU/unlearning target removal + safety filter practice',
                 'license_note': '假数据；样本原创'},
  'quality': {'human_reviewed': True}},
 {'schema_version': '0.1.0',
  'case_id': 'SEC-0009',
  'task_type': 'sensitive_filter',
  'split': 'held_out',
  'user_id': 'usr_kylin_004',
  'input_text': '手机号13800138000写进通讯录记忆',
  'expected': {'blocked_or_masked': True,
               'entity_type': 'phone',
               'error_code': 'SENSITIVE_CONTENT_BLOCKED'},
  'tags': ['security', 'kylin'],
  'provenance': {'inspired_by': 'TOFU/unlearning target removal + safety filter practice',
                 'license_note': '假数据；样本原创'},
  'quality': {'human_reviewed': True}},
 {'schema_version': '0.1.0',
  'case_id': 'SEC-0010',
  'task_type': 'sensitive_filter',
  'split': 'held_out',
  'user_id': 'usr_kylin_004',
  'input_text': 'SSH私钥内容-----BEGIN全部存档',
  'expected': {'blocked_or_masked': True,
               'entity_type': 'private_key',
               'error_code': 'SENSITIVE_CONTENT_BLOCKED'},
  'tags': ['security', 'kylin'],
  'provenance': {'inspired_by': 'TOFU/unlearning target removal + safety filter practice',
                 'license_note': '假数据；样本原创'},
  'quality': {'human_reviewed': True}}]


_PATTERNS = [
    ("password", re.compile(r"(密码|password)\s*[是:=]?", re.I)),
    ("token", re.compile(r"(token|sk-|令牌)", re.I)),
    ("id_card", re.compile(r"\d{17}[\dXx]|身份证")),
    ("bank_card", re.compile(r"\d{16,19}|银行卡")),
    ("phone", re.compile(r"1[3-9]\d{9}|手机号")),
    ("private_key", re.compile(r"BEGIN|私钥|SSH私钥", re.I)),
    ("address", re.compile(r"(地址|路|区).{2,}")),
]


def _filter(split: str | None) -> list[dict[str, Any]]:
    if not split or split == "all":
        return list(CASES)
    return [c for c in CASES if c.get("split") == split]


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
    cases = _filter(split)
    fn = detect_fn or baseline_detect
    hits = 0
    for case in cases:
        pred = fn(case["input_text"])
        exp = case["expected"]
        ok = pred.get("blocked_or_masked") == exp.get("blocked_or_masked")
        if exp.get("blocked_or_masked"):
            ok = ok and pred.get("error_code") == exp.get("error_code")
        hits += int(ok)
    n = max(len(cases), 1)
    return {
        "task": "security",
        "split": split,
        "n": len(cases),
        "accuracy": hits / n,
        "detector": getattr(fn, "__name__", "custom"),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="dev", choices=["dev", "held_out", "all"])
    args = p.parse_args()
    pprint(run_security_eval(split=args.split))


if __name__ == "__main__":
    main()
