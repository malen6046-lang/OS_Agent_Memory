# -*- coding: utf-8 -*-
"""Validate retrieval corpus ↔ query qrels integrity."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import DS, clean_entry_markers, golds_of, load_jsonl  # noqa: E402


def validate() -> list[str]:
    corpus = load_jsonl(DS / "knowledge_corpus.jsonl")
    queries = load_jsonl(DS / "retrieval_queries.jsonl")
    errors: list[str] = []

    ids = [r.get("memory_id") for r in corpus]
    if len(ids) != len(set(ids)):
        errors.append("duplicate memory_id in knowledge_corpus.jsonl")
    id_set = set(ids)

    entry_hits = 0
    missing_topic = 0
    for row in corpus:
        text = row.get("content_text") or ""
        if "条目" in text and "（条目" in text:
            entry_hits += 1
            errors.append(f"{row.get('memory_id')}: content_text still contains 条目 marker")
        if not row.get("canonical_topic_id") and not (row.get("attributes") or {}).get("canonical_topic_id"):
            missing_topic += 1
    if entry_hits:
        errors.append(f"{entry_hits} corpus rows still contain 条目 markers")
    if missing_topic:
        errors.append(f"{missing_topic} corpus rows missing canonical_topic_id")

    # near-dup titles
    titles = Counter()
    for row in corpus:
        if (row.get("status") or "active") != "active":
            continue
        if (row.get("user_id") or "usr_corpus_shared") != "usr_corpus_shared":
            continue
        content = row.get("content") or {}
        title = clean_entry_markers(content.get("title") or "").replace("（补充说明）", "").strip()
        if title:
            titles[title] += 1
    dups = {t: n for t, n in titles.items() if n > 1}
    if dups:
        errors.append(f"duplicate active shared titles remain: {len(dups)} titles")

    split_counts: Counter[str] = Counter()
    no_ans = multi = 0
    for q in queries:
        split_counts[q.get("split") or "?"] += 1
        golds = golds_of(q)
        for g in golds:
            if g not in id_set:
                errors.append(f"{q.get('case_id')}: gold {g} not in corpus")
        if not golds:
            no_ans += 1
            if q.get("split") == "dev" and not (q.get("expected") or {}).get("is_no_answer", False):
                if "no_answer" not in (q.get("tags") or []):
                    errors.append(f"{q.get('case_id')}: empty gold without no_answer tag")
        elif len(golds) >= 2:
            multi += 1

    print("corpus", len(corpus))
    print("queries", len(queries), dict(split_counts))
    print("no_answer", no_ans, "multi_gold", multi)
    print("unique active shared titles", len(titles))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    errs = validate()
    if errs:
        print("FAIL")
        for e in errs[:50]:
            print(" -", e)
        if len(errs) > 50:
            print(f" - ... and {len(errs) - 50} more")
        return 1
    print("OK: qrels validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
