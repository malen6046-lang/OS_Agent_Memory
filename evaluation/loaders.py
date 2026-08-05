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

# Minimal required fields for Dataset V0.1 integrity checks (8_4 P2).
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "preference": ("case_id", "user_id", "split", "expected"),
    "corpus": ("memory_id", "user_id", "content_text"),
    "retrieval": ("case_id", "user_id", "split", "query", "expected"),
    "conflict": ("case_id", "user_id", "split", "old", "new", "expected"),
    "forget": ("case_id", "user_id", "split", "expected_preview", "expected_execute"),
    "security": ("case_id", "user_id", "split", "input_text", "expected"),
}

ID_FIELD: dict[str, str] = {
    "preference": "case_id",
    "corpus": "memory_id",
    "retrieval": "case_id",
    "conflict": "case_id",
    "forget": "case_id",
    "security": "case_id",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise json.JSONDecodeError(
                    f"{path.name}:{lineno}: {exc.msg}",
                    exc.doc,
                    exc.pos,
                ) from exc
    return rows


def validate_rows(task: str, rows: list[dict[str, Any]]) -> list[str]:
    """Return human-readable errors for missing fields / duplicate IDs."""
    if task not in FILES:
        raise KeyError(task)
    errors: list[str] = []
    required = REQUIRED_FIELDS[task]
    id_key = ID_FIELD[task]
    seen: dict[Any, int] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row[{i}]: not an object")
            continue
        for field in required:
            if field not in row:
                errors.append(f"row[{i}]: missing field '{field}'")
        cid = row.get(id_key)
        if cid is None or cid == "":
            errors.append(f"row[{i}]: empty {id_key}")
            continue
        if cid in seen:
            errors.append(f"duplicate {id_key}={cid!r} at row[{seen[cid]}] and row[{i}]")
        else:
            seen[cid] = i
    return errors


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
