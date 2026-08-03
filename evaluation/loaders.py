# -*- coding: utf-8 -*-
"""Load Dataset V0.1 JSONL under evaluation/dataset/."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATASET_DIR = Path(__file__).resolve().parent / "dataset"

FILES = {
    "preference": "preference.jsonl",
    "corpus": "knowledge_corpus.jsonl",
    "retrieval": "retrieval_queries.jsonl",
    "conflict": "conflict.jsonl",
    "forget": "forget.jsonl",
    "security": "security.jsonl",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_cases(task: str, *, split: str | None = "dev") -> list[dict[str, Any]]:
    name = FILES.get(task)
    if not name:
        raise KeyError(task)
    path = DATASET_DIR / name
    if not path.exists():
        raise FileNotFoundError(path)
    rows = load_jsonl(path)
    if task in {"corpus"} or not split or split == "all":
        return rows
    return [r for r in rows if r.get("split") == split]


def load_corpus() -> list[dict[str, Any]]:
    return load_cases("corpus", split="all")
