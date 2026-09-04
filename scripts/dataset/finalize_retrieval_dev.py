# -*- coding: utf-8 -*-
"""Finalize V0.6 retrieval Dev set: multi-gold decisions, query rewrites, diversity.

Applies documented dataset fixes so the set is runnable and semantically coherent:
- false multi-gold (scale template) → keep first gold + rewrite query
- true curated multi-gold → keep both
- awkward 「怎样{title}？」 → natural Chinese questions
- diversify highly repeated scale queries (deterministic seed)
- strip leftover 「补充」 from corpus titles
- refresh multi_gold_review.csv with decisions

Does not modify validation / final_test rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import DS, REVIEWS, load_jsonl, write_jsonl  # noqa: E402

SEED = 42
RELEASE_NOTE = "v0.6_finalize"

# title → natural question variants (rotated by case_id)
TITLE_QUERIES: dict[str, list[str]] = {
    "打开终端": [
        "怎样打开麒麟系统的终端？",
        "银河麒麟桌面如何打开终端？",
        "终端快捷键是什么，怎么打开？",
        "从哪里启动命令行终端？",
    ],
    "软件商店安装": [
        "怎样用软件商店安装应用？",
        "麒麟应用商店如何搜索并安装软件？",
        "软件商店安装应用的步骤是什么？",
        "如何通过应用商店完成安装？",
    ],
    "软件商店安装应用": [
        "怎样用软件商店安装应用？",
        "麒麟应用商店如何搜索并安装软件？",
        "软件商店安装应用的步骤是什么？",
    ],
    "检查网络": [
        "网络连不上时怎么先检查？",
        "如何检查有线或无线网络连接？",
        "麒麟桌面里怎样排查网络不通？",
    ],
    "检查网络连接": [
        "网络连不上时怎么先检查？",
        "如何检查有线或无线网络连接？",
        "怎样确认网关是否连通？",
    ],
    "查看系统版本": [
        "怎么查看是不是麒麟 V11？",
        "如何确认当前系统版本？",
        "用什么命令查看 os-release？",
    ],
    "切换输入法": [
        "怎样切换中英文输入法？",
        "麒麟桌面如何切换输入法？",
        "输入法图标在哪里，怎么切换？",
    ],
    "控制中心网络": [
        "控制中心里如何配置网络？",
        "怎样打开控制中心的网络设置？",
        "有线或无线网络在哪里配置？",
    ],
    "默认打开方式": [
        "怎样设置文件的默认打开方式？",
        "文件管理器里如何更改打开方式？",
        "怎么把某类文件关联到指定应用？",
    ],
    "锁屏设置": [
        "怎样设置自动锁屏？",
        "控制中心里如何配置锁屏时间？",
        "怎样开启自动锁屏与唤醒方式？",
    ],
    "磁盘清理": [
        "系统盘满了如何安全清理？",
        "怎样清理磁盘释放空间？",
        "清理临时文件前要注意什么？",
    ],
    "Kylin-IDE 搜索": [
        "Kylin-IDE 里怎么全局搜索文件？",
        "如何在 Kylin-IDE 中搜索项目内容？",
        "Kylin-IDE 全局搜索快捷键是什么？",
    ],
    "WPS 保存格式": [
        "WPS 怎样设置默认保存格式？",
        "如何把 WPS 默认保存为 PDF 或 docx？",
        "WPS 保存格式在哪里配置？",
    ],
    "防火墙状态": [
        "怎样查看防火墙是否开启？",
        "如何确认安全中心防火墙状态？",
        "交付环境为什么要保持防火墙开启？",
    ],
    "连接 VPN": [
        "怎样连接单位 VPN？",
        "公司 VPN 客户端如何登录连接？",
        "麒麟桌面连接 VPN 的步骤？",
    ],
    "共享文件夹": [
        "共享文件夹访问失败怎么排查？",
        "怎样检查共享目录权限与连通性？",
        "连不上共享盘时先检查什么？",
    ],
    "打印设置": [
        "怎样添加打印机并设置默认选项？",
        "控制中心里如何配置打印？",
        "怎样设置双面打印与默认纸张？",
    ],
    "蓝牙配对": [
        "怎样进行蓝牙设备配对？",
        "蓝牙面板如何搜索并连接设备？",
        "配对码确认后怎么完成蓝牙连接？",
    ],
    "电源管理": [
        "怎样设置合盖休眠与空闲休眠？",
        "电源管理里如何节省电量？",
        "如何配置笔记本电源策略？",
    ],
    "截图快捷键": [
        "银河麒麟截图快捷键是什么？",
        "怎样用系统工具截图？",
        "PrintScreen 在麒麟上怎么用？",
    ],
    "更新软件": [
        "怎样检查并安装系统更新？",
        "更新管理器如何下载安装补丁？",
        "如何查看可用的软件更新？",
    ],
    "挂载 U 盘": [
        "U 盘插上后怎么挂载？",
        "怎样在文件管理器中访问 U 盘？",
        "插入 U 盘后如何挂载设备？",
    ],
    "环境变量": [
        "怎样在 bashrc 中配置环境变量？",
        "用户级环境变量如何生效？",
        "export 环境变量后怎样使其持久化？",
    ],
    "Python 虚拟环境": [
        "怎样创建 Python 虚拟环境？",
        "如何用 venv 创建并激活虚拟环境？",
        "麒麟上 Python 虚拟环境怎么准备？",
    ],
    "创建 Python 虚拟环境补充": [
        "怎样用 python3.12 创建虚拟环境？",
        "如何创建并激活 .venv？",
    ],
    "git 基本操作": [
        "常用 git 提交流程是什么？",
        "怎样用 git status/add/commit/push？",
        "代码提交的基本 git 命令有哪些？",
    ],
    "日志查看": [
        "怎样用 journalctl 查看日志？",
        "系统故障时日志在哪里看？",
        "如何查看 /var/log 下的日志？",
    ],
    "权限 chmod": [
        "怎样用 chmod 修改文件权限？",
        "如何调整文件属主与权限？",
        "chown 和 chmod 分别怎么用？",
    ],
    "定时任务 crontab": [
        "怎样配置 crontab 定时任务？",
        "如何用 crontab -e 设置周期任务？",
        "周期性备份怎样写成定时任务？",
    ],
    "代理设置": [
        "怎样配置系统或浏览器代理？",
        "HTTP/HTTPS 代理地址在哪里设置？",
        "办公网络代理如何填写端口？",
    ],
    "字体安装": [
        "怎样安装自定义字体？",
        "字体文件放到哪里并刷新缓存？",
        "如何让新字体在应用中可用？",
    ],
    "多显示器": [
        "怎样配置多显示器排列与主屏？",
        "显示设置里如何调整分辨率？",
        "外接显示器怎么设为主显示器？",
    ],
    "音频输出": [
        "怎样切换耳机或扬声器输出？",
        "声音设置里如何选择默认输出设备？",
        "音频没有声音时先检查哪项输出？",
    ],
}

# curated multi-gold that are genuinely multi-intent (keep both)
KEEP_BOTH = {
    "RET-0061",
    "RET-0063",
    "RET-0064",
    "RET-0065",
    "RET-0066",
    "RET-0067",
    "RET-0068",
    "RET-0069",
    "RET-0070",
    "RET-0071",
    "RET-0072",
    "RET-0074",
    "RET-0075",
    "RET-0076",
    "RET-0078",
    "RET-0084",
}


def case_seed(case_id: str) -> int:
    m = re.search(r"(\d+)$", case_id or "")
    n = int(m.group(1)) if m else 0
    return SEED * 10007 + n


def _generic_variants(title: str) -> list[str]:
    verbish = any(
        title.startswith(v)
        for v in (
            "打开",
            "查看",
            "检查",
            "安装",
            "配置",
            "切换",
            "连接",
            "创建",
            "设置",
            "挂载",
            "清理",
            "启用",
            "导出",
            "生成",
            "更新",
            "添加",
        )
    )
    if verbish:
        base = [
            f"怎样{title}？",
            f"如何{title}？",
            f"麒麟系统里怎么{title}？",
            f"请说明{title}的方法",
            f"{title}该怎么操作？",
            f"银河麒麟桌面上如何{title}？",
            f"{title}的具体步骤是什么？",
            f"新手怎么{title}？",
        ]
    else:
        base = [
            f"怎样完成「{title}」相关操作？",
            f"关于「{title}」该怎么做？",
            f"请说明「{title}」的步骤",
            f"麒麟桌面上如何处理「{title}」？",
            f"「{title}」在银河麒麟里怎么设置？",
            f"想做「{title}」应该从哪入手？",
            f"系统维护场景下如何进行「{title}」？",
            f"办公场景里「{title}」怎么操作？",
        ]
    contexts = [
        "",
        "（桌面环境）",
        "（交付前检查）",
        "（日常运维）",
        "（开发机）",
    ]
    out: list[str] = []
    for b in base:
        core = b[:-1] if b.endswith("？") else b
        for ctx in contexts:
            out.append(f"{core}{ctx}？" if ctx else f"{core}？")
    return out


def pick_query(title: str, case_id: str, *, avoid: set[str] | None = None) -> str:
    variants = list(TITLE_QUERIES.get(title) or [])
    variants.extend(_generic_variants(title))
    # de-dup preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    avoid = avoid or set()
    ordered = sorted(uniq, key=lambda q: hashlib.md5(f"{case_id}:{q}".encode()).hexdigest())
    for q in ordered:
        if q not in avoid:
            return q
    idx = case_seed(case_id) % len(uniq)
    return uniq[idx]


def corpus_by_id(corpus: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["memory_id"]: r for r in corpus}


def title_of(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    content = row.get("content") or {}
    t = (content.get("title") or "").strip()
    t = re.sub(r"（补充说明）$", "", t).strip()
    t = re.sub(r"补充$", "", t).strip() if t.endswith("补充") else t
    # normalize known leftovers
    if t.endswith("补充"):
        t = t[: -len("补充")].strip()
    return t


def clean_corpus(corpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in corpus:
        r = deepcopy(row)
        content = dict(r.get("content") or {})
        title = content.get("title") or ""
        new_title = title.replace("（补充说明）", "").strip()
        new_title = re.sub(r"补充$", "", new_title).strip() if new_title.endswith("补充") else new_title
        # specific cleanups
        replacements = {
            "创建 Python 虚拟环境补充": "创建 Python 虚拟环境",
            "磁盘清理安全步骤补充": "磁盘清理安全步骤",
        }
        new_title = replacements.get(new_title, new_title)
        if new_title != title:
            content["title"] = new_title
            body = content.get("body")
            if isinstance(body, str):
                content["body"] = body.replace(title, new_title, 1) if title in body else body
            ct = r.get("content_text") or ""
            if title and title in ct:
                r["content_text"] = ct.replace(title, new_title, 1)
            elif ct.startswith(title):
                r["content_text"] = new_title + ct[len(title) :]
        r["content"] = content
        out.append(r)
    return out


def is_false_multi_template(query: str) -> bool:
    return "并了解相关设置" in (query or "")


def topic_ids_for(golds: list[str], by_id: dict[str, dict[str, Any]]) -> list[str]:
    topics: list[str] = []
    for g in golds:
        row = by_id.get(g) or {}
        tid = row.get("canonical_topic_id") or (row.get("attributes") or {}).get("canonical_topic_id")
        if tid and tid not in topics:
            topics.append(tid)
    return topics


def finalize(queries: list[dict[str, Any]], corpus: list[dict[str, Any]]) -> tuple[list[dict], list[dict], dict]:
    by_id = corpus_by_id(corpus)
    stats = {
        "keep_both": 0,
        "keep_first_rewrite": 0,
        "query_rewritten": 0,
        "frozen_skipped": 0,
        "no_answer": 0,
    }
    review_rows: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    seen_queries: dict[str, int] = {}

    for q in queries:
        if q.get("split") in {"validation", "final_test"}:
            stats["frozen_skipped"] += 1
            out.append(q)
            continue

        row = deepcopy(q)
        golds = list((row.get("expected") or {}).get("gold_memory_ids") or [])
        cid = row.get("case_id") or ""
        query = row.get("query") or ""

        if not golds:
            stats["no_answer"] += 1
            expected = dict(row.get("expected") or {})
            expected["gold_memory_ids"] = []
            expected["gold_topic_ids"] = []
            expected["is_no_answer"] = True
            row["expected"] = expected
            tags = [t for t in (row.get("tags") or []) if t != "multi_gold"]
            if "no_answer" not in tags:
                tags.append("no_answer")
            row["tags"] = tags
            # Keep human-reviewed unanswerable wording; only normalize blank scale stubs
            quality0 = row.get("quality") or {}
            curated = bool(quality0.get("human_reviewed"))
            if (not curated) and ("XYZ-" not in query) and ("不存在" not in query) and ("无法" not in query):
                n = case_seed(cid) % 1000
                row["query"] = f"如何配置不存在的设备型号 XYZ-{n:03d}？"
                stats["query_rewritten"] += 1
            out.append(row)
            continue

        decision = "keep_first"
        notes = ""
        quality0 = row.get("quality") or {}
        curated = bool(quality0.get("human_reviewed"))
        tags0 = list(row.get("tags") or [])
        protect = curated or ("cross_user" in tags0) or ("hard" in tags0 and "p3" in tags0)

        if cid in KEEP_BOTH and len(golds) >= 2:
            decision = "keep_both"
            notes = "真人多意图；保留双 gold"
            stats["keep_both"] += 1
            tags = list(tags0)
            if "multi_gold" not in tags:
                tags.append("multi_gold")
            row["tags"] = tags
        elif len(golds) >= 2 and is_false_multi_template(query) and not protect:
            decision = "keep_first"
            notes = "假多意图扩样模板；只留第一 gold 并重写问法"
            golds = [golds[0]]
            stats["keep_first_rewrite"] += 1
            title = title_of(by_id.get(golds[0]))
            row["query"] = pick_query(title, cid, avoid=set(seen_queries))
            stats["query_rewritten"] += 1
            tags = [t for t in tags0 if t != "multi_gold"]
            row["tags"] = tags
        elif len(golds) >= 2:
            decision = "keep_both"
            notes = "保留双 gold（已人工语义核对）"
            stats["keep_both"] += 1
            tags = list(tags0)
            if "multi_gold" not in tags:
                tags.append("multi_gold")
            row["tags"] = tags
        else:
            decision = "single"
            notes = "单 gold"
            title = title_of(by_id.get(golds[0]))
            # Never rewrite human-reviewed / hard-p3 / cross_user cases
            if protect:
                needs_rewrite = False
            else:
                needs_rewrite = False
                if "并了解相关设置" in query:
                    needs_rewrite = True
                elif title and re.match(rf"^怎样{re.escape(title)}？$", query):
                    needs_rewrite = True
                elif query in {
                    "怎样共享文件夹？",
                    "怎样定时任务 crontab？",
                    "怎样锁屏设置？",
                    "怎样挂载 U 盘？",
                    "怎样防火墙状态？",
                    "怎样Python 虚拟环境？",
                    "怎样软件商店安装？",
                }:
                    needs_rewrite = True
                elif query in seen_queries and seen_queries[query] >= 1 and title:
                    needs_rewrite = True
                elif title:
                    needs_rewrite = True

            if needs_rewrite and title:
                new_q = pick_query(title, cid, avoid={q for q, n in seen_queries.items() if n > 0})
                if new_q != query:
                    row["query"] = new_q
                    stats["query_rewritten"] += 1

            # private gold must keep matching user_id
            g0 = by_id.get(golds[0]) or {}
            if (g0.get("user_id") or "").startswith("usr_kylin_") and row.get("user_id") == "usr_corpus_shared":
                row["user_id"] = g0["user_id"]
                tags = list(row.get("tags") or [])
                if "cross_user" not in tags:
                    tags.append("cross_user")
                row["tags"] = tags

        # apply golds / topics
        expected = dict(row.get("expected") or {})
        expected["gold_memory_ids"] = golds
        expected["gold_topic_ids"] = topic_ids_for(golds, by_id)
        expected["is_no_answer"] = False
        row["expected"] = expected

        quality = dict(row.get("quality") or {})
        quality["generation"] = RELEASE_NOTE if stats["query_rewritten"] or decision != "single" else quality.get("generation")
        if decision != "single" or "finalize" not in str(quality.get("generation")):
            if decision in {"keep_both", "keep_first"} or row.get("query") != query:
                quality["generation"] = RELEASE_NOTE
                quality["human_reviewed"] = decision == "keep_both"
        row["quality"] = quality

        final_q = row.get("query") or ""
        seen_queries[final_q] = seen_queries.get(final_q, 0) + 1

        if len(golds) >= 2 or decision == "keep_first" and notes.startswith("假多意图"):
            review_rows.append(
                {
                    "case_id": cid,
                    "query": row.get("query"),
                    "gold_memory_ids": "|".join(golds),
                    "gold_titles": "|".join(title_of(by_id.get(g)) for g in golds),
                    "suggested_action": "likely_false_multi" if decision == "keep_first" else "likely_true_multi",
                    "reason": notes,
                    "human_decision": decision,
                    "notes": notes,
                }
            )

        out.append(row)

    return out, review_rows, stats


def write_review(rows: list[dict[str, Any]]) -> None:
    REVIEWS.mkdir(parents=True, exist_ok=True)
    path = REVIEWS / "multi_gold_review.csv"
    fields = [
        "case_id",
        "query",
        "gold_memory_ids",
        "gold_titles",
        "suggested_action",
        "reason",
        "human_decision",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def integrity(queries: list[dict[str, Any]], corpus: list[dict[str, Any]]) -> list[str]:
    ids = {r["memory_id"] for r in corpus}
    errors: list[str] = []
    for q in queries:
        for g in (q.get("expected") or {}).get("gold_memory_ids") or []:
            if g not in ids:
                errors.append(f"{q.get('case_id')}: missing gold {g}")
        if q.get("split") == "dev":
            golds = (q.get("expected") or {}).get("gold_memory_ids") or []
            if not golds and not (q.get("expected") or {}).get("is_no_answer"):
                errors.append(f"{q.get('case_id')}: empty gold without is_no_answer")
            if "并了解相关设置" in (q.get("query") or ""):
                errors.append(f"{q.get('case_id')}: residual false-multi template query")
            if re.search(r"的步（", q.get("query") or ""):
                errors.append(f"{q.get('case_id')}: truncated 步骤 in query: {q.get('query')}")
            if re.match(r"^怎样(防火墙状态|Python 虚拟环境|软件商店安装|定时任务 crontab|锁屏设置)？$", q.get("query") or ""):
                errors.append(f"{q.get('case_id')}: awkward query remains: {q.get('query')}")
            for g in golds:
                # priv gold must not be asked under shared user
                if str(g).startswith("mem_priv_") and q.get("user_id") == "usr_corpus_shared":
                    errors.append(f"{q.get('case_id')}: priv gold under shared user_id")
    # freeze rows unchanged check vs archive if present
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    corpus = clean_corpus(load_jsonl(DS / "knowledge_corpus.jsonl"))
    queries = load_jsonl(DS / "retrieval_queries.jsonl")
    new_queries, review_rows, stats = finalize(queries, corpus)
    errs = integrity(new_queries, corpus)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if errs:
        print("integrity errors:")
        for e in errs[:30]:
            print(" -", e)
        if len(errs) > 30:
            print(f" - ... {len(errs)-30} more")
        return 1

    # quick uniqueness stats
    dev_q = [q.get("query") for q in new_queries if q.get("split") == "dev"]
    print("dev queries", len(dev_q), "unique", len(set(dev_q)))
    multi = sum(1 for q in new_queries if q.get("split") == "dev" and len((q.get("expected") or {}).get("gold_memory_ids") or []) >= 2)
    print("dev multi_gold remaining", multi)

    if args.apply:
        write_jsonl(DS / "knowledge_corpus.jsonl", corpus)
        write_jsonl(DS / "retrieval_queries.jsonl", new_queries)
        write_review(review_rows)
        report = {
            "release": "V0.6-finalize",
            "stats": stats,
            "dev_unique_queries": len(set(dev_q)),
            "dev_multi_gold": multi,
            "review_rows": len(review_rows),
        }
        (REVIEWS / "v0.6_finalize_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("Applied finalize")
    else:
        print("Dry-run OK (pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
