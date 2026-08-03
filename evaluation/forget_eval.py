# -*- coding: utf-8 -*-
"""Forget eval — preview + in-memory execute/residual checks (dataset/forget.jsonl)."""
from __future__ import annotations

import argparse
import hashlib
from copy import deepcopy
from pprint import pprint
from typing import Any, Callable

from evaluation.loaders import load_cases
from evaluation.metrics import precision_recall


def make_confirmation_token(case: dict[str, Any]) -> str:
    """Derive token from case_id (NOT copied from gold expected fields)."""
    raw = f"{case['case_id']}:{case.get('user_id','')}:{case.get('instruction','')}"
    return "tok_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def baseline_preview(case: dict[str, Any]) -> dict[str, Any]:
    instr = case.get("instruction", "")
    delete, keep = [], []
    for fx in case.get("memory_fixtures", []):
        mid = fx["memory_id"]
        hit = "全部记忆" in instr or "忘记全部" in instr
        if not hit:
            for frag, words in (
                ("fmt", ["格式", "输出"]),
                ("fw", ["防火墙"]),
                ("proxy", ["代理"]),
                ("theme", ["主题"]),
                ("browser", ["浏览器"]),
                ("secret", ["密码", "私钥"]),
                ("pdf", ["PDF", "pdf"]),
                ("dns", ["DNS", "dns"]),
                ("vpn", ["VPN", "vpn"]),
                ("debug", ["调试", "端口"]),
                ("bt", ["蓝牙"]),
                ("table", ["表格"]),
                ("project", ["会议", "星河"]),
                ("temp", ["临时"]),
                ("lock", ["锁屏"]),
                ("verbosity", ["简洁", "详细", "风格"]),
                ("ip", ["IP", "账号"]),
                ("install", ["安装"]),
                ("markdown", ["Markdown", "markdown"]),
                ("token", ["token", "令牌"]),
                ("editor", ["编辑器", "IDE"]),
                ("backup", ["备份"]),
                ("minutes", ["纪要"]),
                ("wps", ["WPS"]),
                ("audio", ["音频"]),
                ("zh", ["中文"]),
            ):
                if frag in mid and any(w.lower() in instr.lower() for w in words):
                    hit = True
                    break
        (delete if hit else keep).append(mid)
    return {
        "should_delete_ids": delete,
        "should_keep_ids": keep,
        "confirmation_token": make_confirmation_token(case),
        "confirmation_required": bool(case.get("requires_second_confirm")),
    }


def simulate_execute(
    case: dict[str, Any],
    preview: dict[str, Any],
    *,
    drop_collection: bool = False,
) -> dict[str, Any]:
    """In-memory execute: tombstone deleted ids; check residuals & DropCollection ban."""
    if drop_collection:
        raise RuntimeError("DropCollection is forbidden by V1.2.1/V1.2.2")
    store = {fx["memory_id"]: deepcopy(fx) for fx in case.get("memory_fixtures", [])}
    vector_index = {mid: True for mid in store}  # presence map
    token = preview["confirmation_token"]
    expected_token = make_confirmation_token(case)
    if token != expected_token:
        return {
            "ok": False,
            "error": "confirmation_token_mismatch",
            "deleted_ids": [],
            "residual_in_sqlite": True,
            "residual_in_vector": True,
            "false_delete_ids": [],
            "drop_collection_forbidden": True,
            "status_after": None,
        }
    gold_keep = set(case["expected_preview"].get("should_keep_ids", []))
    delete_ids = list(preview.get("should_delete_ids", []))
    false_delete = []
    for mid in delete_ids:
        if mid in gold_keep:
            false_delete.append(mid)
        if mid in store:
            store[mid]["status"] = "tombstoned"
            vector_index.pop(mid, None)
    residual_sql = any(
        mid in store and store[mid].get("status") == "active" for mid in delete_ids
    ) or any(mid not in store for mid in delete_ids)
    residual_vec = any(mid in vector_index for mid in delete_ids)
    return {
        "ok": True,
        "deleted_ids": delete_ids,
        "status_after": "tombstoned",
        "residual_in_sqlite": residual_sql,
        "residual_in_vector": residual_vec,
        "false_delete_ids": false_delete,
        "drop_collection_forbidden": True,
        "store_snapshot": {
            mid: rec.get("status") for mid, rec in store.items()
        },
    }


def run_forget_eval(
    *,
    split: str = "dev",
    preview_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cases = load_cases("forget", split=split)
    fn = preview_fn or baseline_preview
    precs, recs = [], []
    false_del = 0
    exec_ok = residual_fail = 0
    for case in cases:
        # gold lists for scoring (token NOT taken from gold)
        gold_del = case["expected_preview"]["should_delete_ids"]
        gold_keep = set(case["expected_preview"].get("should_keep_ids", []))
        pred = fn(case)
        p, r = precision_recall(pred.get("should_delete_ids", []), gold_del)
        precs.append(p)
        recs.append(r)
        false_del += len(set(pred.get("should_delete_ids", [])) & gold_keep)
        exe = simulate_execute(case, pred)
        if exe.get("ok") and not exe["residual_in_sqlite"] and not exe["residual_in_vector"]:
            # score execute against gold delete set
            if set(exe["deleted_ids"]) == set(gold_del):
                exec_ok += 1
            if exe["false_delete_ids"]:
                residual_fail += 1
        else:
            residual_fail += 1
        assert case["expected_execute"].get("drop_collection_forbidden") is True
        assert case["expected_execute"].get("status_after") == "tombstoned"
    n = max(len(cases), 1)
    return {
        "task": "forget",
        "split": split,
        "n": len(cases),
        "preview_precision": sum(precs) / n,
        "preview_recall": sum(recs) / n,
        "false_delete_count": false_del,
        "execute_success_rate": exec_ok / n,
        "residual_or_false_delete_fail_rate": residual_fail / n,
        "confirmation_token_scheme": "sha256(case_id:user:instruction)",
        "drop_collection_forbidden": True,
        "resolver": getattr(fn, "__name__", "custom"),
        "status": "baseline_not_competition_claim",
        "note": "execute is in-memory tombstone simulation until ForgetService Real is wired",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="dev", choices=["dev", "held_out", "all"])
    args = p.parse_args()
    pprint(run_forget_eval(split=args.split))


if __name__ == "__main__":
    main()
