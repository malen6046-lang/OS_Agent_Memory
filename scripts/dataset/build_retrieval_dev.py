# -*- coding: utf-8 -*-
"""Rebuild diversified Dev retrieval queries on top of a canonical corpus.

Does **not** touch validation / final_test.
Keeps existing frozen case_ids and existing non-scale curated Dev queries by default;
only regenerates queries whose quality.generation is a scale/remap tag, or use --all-dev.

Usage:
  python scripts/dataset/build_retrieval_dev.py --dry-run
  python scripts/dataset/build_retrieval_dev.py --apply --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import DS, golds_of, load_jsonl, set_golds, write_jsonl  # noqa: E402

QUERY_TEMPLATES = [
    "怎样{title}？",
    "如何{title}？",
    "{title}的步骤是什么？",
    "麒麟系统里怎么{title}？",
    "请说明{title}的方法",
    "{kw}相关操作怎么做？",
    "银河麒麟桌面上如何{title}？",
    "{title}该怎么操作？",
]

SCALE_GEN = {
    "v0.5_scale_expand",
    "v0.6_remap",
    "v0.6_rebuild",
}


def active_shared(corpus: list[dict]) -> list[dict]:
    return [
        c
        for c in corpus
        if c.get("status", "active") == "active" and c.get("user_id") == "usr_corpus_shared"
    ]


def make_query_text(rng: random.Random, title: str, kws: list[str]) -> str:
    tmpl = rng.choice(QUERY_TEMPLATES)
    kw = kws[0] if kws else title
    return tmpl.format(title=title, kw=kw)


def rebuild(seed: int, all_dev: bool) -> tuple[list[dict], dict]:
    corpus = load_jsonl(DS / "knowledge_corpus.jsonl")
    queries = load_jsonl(DS / "retrieval_queries.jsonl")
    active = active_shared(corpus)
    if not active:
        raise SystemExit("no active shared corpus")

    rng = random.Random(seed)
    stats = {"kept": 0, "rebuilt": 0, "frozen": 0, "no_answer_kept": 0}
    out: list[dict] = []

    for q in queries:
        if q.get("split") in {"validation", "final_test"}:
            stats["frozen"] += 1
            out.append(q)
            continue

        golds = golds_of(q)
        gen = (q.get("quality") or {}).get("generation")
        should = all_dev or gen in SCALE_GEN
        if not should or not golds:
            if not golds:
                stats["no_answer_kept"] += 1
            else:
                stats["kept"] += 1
            out.append(q)
            continue

        # rebuild wording but keep first gold (and any extra golds if multi)
        primary = next((c for c in active if c["memory_id"] == golds[0]), None)
        if primary is None:
            stats["kept"] += 1
            out.append(q)
            continue

        row = deepcopy(q)
        title = ((primary.get("content") or {}).get("title") or "相关操作").replace("（补充说明）", "")
        kws = list((primary.get("content") or {}).get("keywords") or [title])
        if len(golds) >= 2:
            row["query"] = f"如何完成「{title}」，并说明相关设置要点？"
            tags = list(row.get("tags") or [])
            if "multi_gold" not in tags:
                tags.append("multi_gold")
            row["tags"] = tags
        else:
            row["query"] = make_query_text(rng, title, kws)
        topics = []
        for g in golds:
            hit = next((c for c in corpus if c["memory_id"] == g), None)
            tid = (hit or {}).get("canonical_topic_id") or ((hit or {}).get("attributes") or {}).get(
                "canonical_topic_id"
            )
            if tid and tid not in topics:
                topics.append(tid)
        expected = dict(row.get("expected") or {})
        expected["gold_memory_ids"] = golds
        expected["gold_topic_ids"] = topics
        expected["is_no_answer"] = False
        row["expected"] = expected
        quality = dict(row.get("quality") or {})
        quality["generation"] = "v0.6_rebuild"
        quality["rebuild_seed"] = seed
        row["quality"] = quality
        stats["rebuilt"] += 1
        out.append(row)

    return out, stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all-dev", action="store_true", help="rebuild all answerable Dev queries")
    args = parser.parse_args()
    if not args.apply and not args.dry_run:
        args.dry_run = True

    rows, stats = rebuild(args.seed, args.all_dev)
    print(json.dumps(stats, ensure_ascii=False))
    if args.apply:
        write_jsonl(DS / "retrieval_queries.jsonl", rows)
        print("Applied retrieval_queries.jsonl rebuild")
    else:
        print("Dry-run only (pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
