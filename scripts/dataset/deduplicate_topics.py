# -*- coding: utf-8 -*-
"""Deduplicate Dev knowledge corpus and remap retrieval qrels (V0.6).

Rules
-----
- One canonical MemoryRecord per normalized topic title (strip 「条目 N」 / 「补充说明」).
- Remove 「条目 N」 pollution from embedding text (content_text / content.body).
- Attach ``canonical_topic_id`` on corpus; ``expected.gold_topic_ids`` on queries.
- Remap only ``split=dev`` retrieval golds; validation / final_test rows untouched.
- Keep special memories (private / inactive / tombstoned) always.
- Prefer frozen gold memory_ids, else lowest ``mem_kb_*`` as canonical.

Usage
-----
  python scripts/dataset/deduplicate_topics.py          # dry-run report
  python scripts/dataset/deduplicate_topics.py --apply  # write dataset + reviews
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    DS,
    REVIEWS,
    clean_entry_markers,
    golds_of,
    is_special_memory,
    load_jsonl,
    memory_num,
    normalize_title,
    set_golds,
    topic_id_for,
    write_jsonl,
)

RELEASE = "V0.6-retrieval-dedupe"
BATCH = "v0.6_dedupe"
ARCHIVE = DS / "archive" / "v0.5_pre_dedupe"


def load_frozen_gold_ids(queries: list[dict[str, Any]]) -> set[str]:
    frozen: set[str] = set()
    for q in queries:
        if q.get("split") in {"validation", "final_test"}:
            frozen.update(golds_of(q))
    return frozen


def record_title(row: dict[str, Any]) -> str:
    content = row.get("content") or {}
    return normalize_title(content.get("title"), row.get("content_text"))


def clean_corpus_row(row: dict[str, Any], *, topic_id: str, batch: str) -> dict[str, Any]:
    out = deepcopy(row)
    out["content_text"] = clean_entry_markers(out.get("content_text"))
    content = dict(out.get("content") or {})
    if "title" in content:
        content["title"] = normalize_title(content.get("title"), out.get("content_text"))
    if "body" in content and isinstance(content["body"], str):
        content["body"] = clean_entry_markers(content["body"])
    # drop synthetic kbN keyword noise from scale expand
    kws = content.get("keywords")
    if isinstance(kws, list):
        content["keywords"] = [k for k in kws if not (isinstance(k, str) and k.startswith("kb") and k[2:].isdigit())]
    out["content"] = content
    attrs = dict(out.get("attributes") or {})
    attrs["canonical_topic_id"] = topic_id
    attrs["generation_batch"] = attrs.get("generation_batch") or attrs.get("batch") or batch
    attrs["batch"] = batch
    # keep original scale marker if present
    if "domain" not in attrs:
        attrs["domain"] = "kylin_desktop"
    out["attributes"] = attrs
    out["canonical_topic_id"] = topic_id
    return out


def choose_canonical(
    items: list[dict[str, Any]],
    frozen_golds: set[str],
) -> dict[str, Any]:
    for row in items:
        if row["memory_id"] in frozen_golds:
            return row
    kb = [r for r in items if memory_num(r["memory_id"]) < 10**9]
    pool = kb or items
    return min(pool, key=lambda r: (memory_num(r["memory_id"]), r["memory_id"]))


def build_topic_groups(corpus: list[dict[str, Any]]) -> tuple[dict[str, list[dict]], list[dict]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    specials: list[dict[str, Any]] = []
    for row in corpus:
        if is_special_memory(row):
            specials.append(row)
            continue
        title = record_title(row)
        key = title or row["memory_id"]
        groups[key].append(row)
    return groups, specials


def suggest_multi_action(query: str, tags: list[str], gold_titles: list[str]) -> tuple[str, str]:
    q = query or ""
    if "并了解相关设置" in q or ("怎样" in q and "并了解" in q):
        return (
            "likely_false_multi",
            "扩样模板「怎样{title}并了解相关设置？」疑似假多意图；建议只保留第一 gold，或重写 query。",
        )
    if any(x in q for x in ("分别", "以及", "并且", "同时", "一边", "另一")):
        return ("likely_true_multi", "Query 含并列意图信号；若两主题均相关则保留双 gold。")
    if len(set(gold_titles)) < 2:
        return ("collapse_same_topic", "多 gold 去重后落在同一主题；应合并为单 gold。")
    if "multi_gold" in tags:
        return ("needs_human_review", "带 multi_gold 标签；请人工确认第二 gold 是否与 query 对应。")
    return ("needs_human_review", "请人工复核第二 gold 与 query 语义是否匹配。")


def remediate(
    corpus: list[dict[str, Any]],
    queries: list[dict[str, Any]],
) -> dict[str, Any]:
    frozen_golds = load_frozen_gold_ids(queries)
    groups, specials = build_topic_groups(corpus)

    id_to_canonical: dict[str, str] = {}
    id_to_topic: dict[str, str] = {}
    new_corpus: list[dict[str, Any]] = []
    topic_report: list[dict[str, Any]] = []

    for title, items in sorted(groups.items(), key=lambda x: x[0]):
        canon_src = choose_canonical(items, frozen_golds)
        topic_id = topic_id_for(canon_src["memory_id"], title)
        cleaned = clean_corpus_row(canon_src, topic_id=topic_id, batch=BATCH)
        new_corpus.append(cleaned)
        for item in items:
            id_to_canonical[item["memory_id"]] = cleaned["memory_id"]
            id_to_topic[item["memory_id"]] = topic_id
        topic_report.append(
            {
                "canonical_topic_id": topic_id,
                "title": title,
                "canonical_memory_id": cleaned["memory_id"],
                "variant_count": len(items),
                "dropped_ids": [i["memory_id"] for i in items if i["memory_id"] != cleaned["memory_id"]],
            }
        )

    for row in specials:
        title = record_title(row)
        topic_id = topic_id_for(row["memory_id"], title or row["memory_id"])
        cleaned = clean_corpus_row(row, topic_id=topic_id, batch=BATCH)
        # keep original batch markers for specials when useful
        new_corpus.append(cleaned)
        id_to_canonical[row["memory_id"]] = cleaned["memory_id"]
        id_to_topic[row["memory_id"]] = topic_id

    # stable order: mem_kb numeric then others
    def sort_key(r: dict[str, Any]) -> tuple[int, str]:
        return (memory_num(r["memory_id"]), r["memory_id"])

    new_corpus.sort(key=sort_key)

    new_queries: list[dict[str, Any]] = []
    remap_stats = {
        "dev_total": 0,
        "dev_gold_remapped": 0,
        "dev_multi_collapsed": 0,
        "dev_no_answer": 0,
        "frozen_untouched": 0,
    }
    multi_review_rows: list[dict[str, Any]] = []
    mid_to_title = {r["memory_id"]: record_title(r) for r in new_corpus}

    for q in queries:
        row = deepcopy(q)
        split = row.get("split")
        golds = golds_of(row)
        if split in {"validation", "final_test"}:
            # Freeze check hashes these rows — do not alter any field.
            remap_stats["frozen_untouched"] += 1
            new_queries.append(q)
            continue

        remap_stats["dev_total"] += 1
        if not golds:
            remap_stats["dev_no_answer"] += 1
            expected = dict(row.get("expected") or {})
            expected["gold_memory_ids"] = []
            expected["gold_topic_ids"] = []
            expected["is_no_answer"] = True
            row["expected"] = expected
            tags = list(row.get("tags") or [])
            if "no_answer" not in tags:
                tags.append("no_answer")
            row["tags"] = tags
            new_queries.append(row)
            continue

        new_golds: list[str] = []
        topics: list[str] = []
        changed = False
        for g in golds:
            cg = id_to_canonical.get(g, g)
            if cg != g:
                changed = True
            if cg not in new_golds:
                new_golds.append(cg)
            tid = id_to_topic.get(cg) or id_to_topic.get(g)
            if tid and tid not in topics:
                topics.append(tid)
        if len(new_golds) < len(golds):
            remap_stats["dev_multi_collapsed"] += 1
            changed = True
        if changed:
            remap_stats["dev_gold_remapped"] += 1

        set_golds(row, new_golds)
        expected = dict(row.get("expected") or {})
        expected["gold_topic_ids"] = topics
        expected["is_no_answer"] = False
        row["expected"] = expected

        # light query cleanup: drop 补充说明 noise in generated questions
        if isinstance(row.get("query"), str) and "（补充说明）" in row["query"]:
            row["query"] = row["query"].replace("（补充说明）", "")

        if len(new_golds) >= 2:
            titles = [mid_to_title.get(g, "") for g in new_golds]
            action, reason = suggest_multi_action(row.get("query") or "", list(row.get("tags") or []), titles)
            tags = list(row.get("tags") or [])
            if "multi_gold" not in tags:
                tags.append("multi_gold")
            row["tags"] = tags
            multi_review_rows.append(
                {
                    "case_id": row.get("case_id"),
                    "query": row.get("query"),
                    "gold_memory_ids": "|".join(new_golds),
                    "gold_titles": "|".join(titles),
                    "suggested_action": action,
                    "reason": reason,
                    "human_decision": "",
                    "notes": "",
                }
            )

        prov = dict(row.get("provenance") or {})
        if "adaptation" in prov:
            prov["adaptation"] = f"{prov['adaptation']}; {RELEASE} gold remap"
        else:
            prov["adaptation"] = f"{RELEASE} gold remap"
        row["provenance"] = prov
        quality = dict(row.get("quality") or {})
        quality["generation"] = quality.get("generation") or "v0.6_remap"
        row["quality"] = quality
        new_queries.append(row)

    kept_ids = {r["memory_id"] for r in new_corpus}
    missing_frozen = sorted(frozen_golds - kept_ids)

    return {
        "release": RELEASE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_before": len(corpus),
        "corpus_after": len(new_corpus),
        "topics": len(topic_report),
        "specials_kept": len(specials),
        "dropped_memory_ids": sum(len(t["dropped_ids"]) for t in topic_report),
        "remap_stats": remap_stats,
        "missing_frozen_golds": missing_frozen,
        "multi_gold_review_count": len(multi_review_rows),
        "topic_report": topic_report,
        "new_corpus": new_corpus,
        "new_queries": new_queries,
        "multi_review_rows": multi_review_rows,
        "id_to_canonical": id_to_canonical,
    }


def archive_originals() -> None:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    for name in ("knowledge_corpus.jsonl", "retrieval_queries.jsonl"):
        src = DS / name
        dst = ARCHIVE / name
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)


def write_outputs(result: dict[str, Any], *, apply: bool) -> None:
    REVIEWS.mkdir(parents=True, exist_ok=True)
    report = {k: v for k, v in result.items() if k not in {"new_corpus", "new_queries", "multi_review_rows", "id_to_canonical"}}
    report_path = REVIEWS / "v0.6_remediation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    mapping_path = REVIEWS / "v0.6_id_to_canonical.json"
    mapping_path.write_text(
        json.dumps(result["id_to_canonical"], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    csv_path = REVIEWS / "multi_gold_review.csv"
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
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in result["multi_review_rows"]:
            writer.writerow(row)

    md_path = REVIEWS / "multi_gold_review.md"
    lines = [
        f"# Multi-gold 人工复核清单（{RELEASE}）",
        "",
        f"共 **{len(result['multi_review_rows'])}** 条。请在 CSV 同名字段填写 `human_decision`：`keep_both` / `keep_first` / `rewrite_query`。",
        "",
        "| case_id | suggested | query | golds |",
        "|---------|-----------|-------|-------|",
    ]
    for row in result["multi_review_rows"]:
        q = (row["query"] or "").replace("|", "\\|")
        lines.append(
            f"| {row['case_id']} | {row['suggested_action']} | {q} | {row['gold_titles']} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote report: {report_path}")
    print(f"Wrote mapping: {mapping_path}")
    print(f"Wrote multi-gold review: {csv_path}")
    print(
        f"corpus {result['corpus_before']} -> {result['corpus_after']} "
        f"(topics={result['topics']}, dropped={result['dropped_memory_ids']})"
    )
    print(f"remap_stats: {json.dumps(result['remap_stats'], ensure_ascii=False)}")
    print(f"multi_gold_review_count: {result['multi_gold_review_count']}")
    if result["missing_frozen_golds"]:
        print("ERROR missing frozen golds:", result["missing_frozen_golds"])

    if apply:
        if result["missing_frozen_golds"]:
            raise SystemExit("Refusing to apply: frozen gold memory_ids missing from new corpus")
        archive_originals()
        write_jsonl(DS / "knowledge_corpus.jsonl", result["new_corpus"])
        write_jsonl(DS / "retrieval_queries.jsonl", result["new_queries"])
        print(f"Applied. Archive at {ARCHIVE}")


def main() -> int:
    parser = argparse.ArgumentParser(description="V0.6 retrieval corpus dedupe + qrel remap")
    parser.add_argument("--apply", action="store_true", help="write knowledge_corpus.jsonl and retrieval_queries.jsonl")
    args = parser.parse_args()

    corpus = load_jsonl(DS / "knowledge_corpus.jsonl")
    queries = load_jsonl(DS / "retrieval_queries.jsonl")
    if not corpus or not queries:
        raise SystemExit(f"missing dataset under {DS}")

    result = remediate(corpus, queries)
    write_outputs(result, apply=args.apply)
    return 1 if result["missing_frozen_golds"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
