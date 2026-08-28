# -*- coding: utf-8 -*-
"""Ad-hoc dataset quality audit beyond check_ground_truth."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

DS = Path(__file__).resolve().parents[1] / "evaluation" / "dataset"


def load(name: str) -> list[dict]:
    return [
        json.loads(l)
        for l in (DS / name).read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]


def main() -> None:
    forg = load("forget.jsonl")
    print("=== PLACEHOLDER tokens ===")
    for r in forg:
        blob = json.dumps(r, ensure_ascii=False)
        if "PLACEHOLDER" in blob:
            print(
                r["case_id"],
                r["split"],
                "preview=",
                r["expected_preview"].get("confirmation_token"),
                "exec=",
                r["expected_execute"].get("confirmation_token"),
            )

    conf = load("conflict.jsonl")
    print("\n=== conflict relation coverage ===")
    print(Counter((r["split"], r["expected"]["relation"]) for r in conf))
    print("\n=== conflict dev rows ===")
    for r in conf:
        if r["split"] != "dev":
            continue
        old, new, exp = r["old"], r["new"], r["expected"]
        ov = (old.get("content") or {}).get("value")
        nv = (new.get("content") or {}).get("value")
        ok = (old.get("content") or {}).get("preference_key")
        nk = (new.get("content") or {}).get("preference_key")
        print(
            f"{r['case_id']} {exp['relation']}/{exp['strategy']} "
            f"key={ok}->{nk} val={ov}->{nv} "
            f"vf={old.get('valid_from')[-8:]}->{new.get('valid_from')[-8:]} "
            f"c={old.get('confidence')}/{new.get('confidence')} "
            f"r={old.get('revision')}/{new.get('revision')}"
        )

    pref = load("preference.jsonl")
    ep = re.compile(r"(这次|临时|仅本次|下次不用|只要这一次|仅限本次)")
    print("\n=== preference ephemeral (dev, untagged) ===")
    for r in pref:
        if r["split"] != "dev":
            continue
        ut = r.get("utterance", "")
        golds = r.get("expected_preferences") or []
        tags = " ".join(r.get("tags") or [])
        if ep.search(ut) and golds and "ephemeral" not in tags and "临时" not in tags:
            print(r["case_id"], ut[:48], "n_gold=", len(golds))
    empty = [r["case_id"] for r in pref if not (r.get("expected_preferences") or [])]
    print("pref empty gold:", len(empty), empty)

    ret = load("retrieval_queries.jsonl")
    corpus_rows = load("knowledge_corpus.jsonl")
    corpus = {c["memory_id"]: c for c in corpus_rows}
    print("\n=== retrieval ===")
    print("empty_gold", sum(1 for r in ret if not r.get("gold_memory_ids")))
    print("multi_gold", sum(1 for r in ret if len(r.get("gold_memory_ids") or []) >= 2))
    inactive_gold = []
    for r in ret:
        for gid in r.get("gold_memory_ids") or []:
            st = corpus.get(gid, {}).get("status")
            if st and st != "active":
                inactive_gold.append((r["case_id"], gid, st, r["split"]))
    print("inactive_as_gold", inactive_gold)

    print("\n=== corpus ===")
    print(Counter(c.get("status") for c in corpus.values()))
    empty_txt = [mid for mid, c in corpus.items() if not (c.get("content_text") or "").strip()]
    print("empty content_text", empty_txt)
    valid_sub = {
        "output_style",
        "operation_habit",
        "security_policy",
        "workflow",
        "case",
        "template",
        "fact",
    }
    bad_sub = [(mid, c.get("subtype")) for mid, c in corpus.items() if c.get("subtype") not in valid_sub]
    print("bad subtype", bad_sub)

    sec = load("security.jsonl")
    print("\n=== security odd patterns (dev) ===")
    for r in sec:
        if r["split"] != "dev":
            continue
        exp = r.get("expected") or {}
        text = r.get("input_text", "")
        if re.search(r"(密码|password|token|私钥|身份证|银行卡)", text, re.I) and not exp.get(
            "blocked_or_masked"
        ):
            print("sensitive_text_not_blocked", r["case_id"], text[:60], exp)
        if exp.get("blocked_or_masked") and not re.search(
            r"(密码|password|token|密钥|私钥|身份证|银行卡|手机号|账号|口令)", text, re.I
        ):
            print("blocked_without_obvious_entity", r["case_id"], text[:60], exp)

    # forget: instruction keyword vs delete fixture topic rough check
    print("\n=== forget delete fixture topic presence (dev) ===")
    hints = {
        "输出格式": ["输出", "Markdown", "格式"],
        "防火墙": ["防火墙"],
        "锁屏": ["锁屏"],
        "代理": ["代理"],
        "token": ["令牌", "token", "Token"],
        "星河": ["星河"],
        "浏览器": ["浏览器", "Firefox"],
        "密码": ["密码"],
        "英文": ["英文"],
        "DNS": ["DNS"],
        "PDF": ["PDF"],
        "调试端口": ["调试端口", "8080"],
        "浅色": ["浅色"],
        "安装失败": ["安装失败", "失败"],
        "周报": ["周报"],
        "注释": ["注释"],
        "清理": ["清理"],
        "深色": ["深色"],
        "输入法": ["输入法"],
        "会议专项": ["会议", "专项"],
        "专项细节": ["会议", "专项", "细节"],
        "蓝牙": ["蓝牙"],  # FORG-0022 should NOT match fixtures
    }
    for r in forg:
        if r["split"] != "dev":
            continue
        inst = r["instruction"]
        dels = set(r["expected_preview"]["should_delete_ids"])
        del_texts = " ".join(
            fx["content_text"] for fx in r["memory_fixtures"] if fx["memory_id"] in dels
        )
        keep_texts = " ".join(
            fx["content_text"] for fx in r["memory_fixtures"] if fx["memory_id"] not in dels
        )
        matched_hint = None
        for k, kws in hints.items():
            if k in inst:
                matched_hint = (k, kws)
                break
        if matched_hint is None:
            continue
        k, kws = matched_hint
        hit_del = any(w in del_texts for w in kws)
        hit_keep_only = (not hit_del) and any(w in keep_texts for w in kws)
        if r["case_id"] == "FORG-0022":
            # expected empty delete; fixtures must not match bluetooth
            bad = any(w in (del_texts + " " + keep_texts) for w in kws)
            print(
                r["case_id"],
                "boundary_bluetooth",
                "fixture_mentions_bluetooth=" + str(bad),
                "delete_empty=" + str(len(dels) == 0),
            )
            continue
        if dels and not hit_del:
            print(
                "WEAK_ALIGN",
                r["case_id"],
                "hint=",
                k,
                "inst=",
                inst,
                "del_texts=",
                del_texts[:80],
            )
        if hit_keep_only and dels:
            print("KEEP_HAS_HINT_DEL_MISS", r["case_id"], k)

    # duplicate memory_ids across forget cases ok; check freeze manifest
    man = json.loads((DS / "freeze_manifest.json").read_text(encoding="utf-8"))
    print("\n=== freeze manifest keys ===", list(man.keys())[:8])


if __name__ == "__main__":
    main()
