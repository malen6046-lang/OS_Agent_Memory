# -*- coding: utf-8 -*-
"""Shared helpers for retrieval dataset remediation scripts."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "evaluation" / "dataset"
REVIEWS = DS / "reviews"

ENTRY_RE = re.compile(r"\s*适用银河麒麟\s*V11\s*桌面场景（条目\s*\d+）。?\s*")
ENTRY_INLINE_RE = re.compile(r"（条目\s*\d+）")
SUPPLEMENT_RE = re.compile(r"（补充说明）\s*$")
WS_RE = re.compile(r"\s+")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def clean_entry_markers(text: str | None) -> str:
    t = ENTRY_RE.sub("", text or "")
    t = ENTRY_INLINE_RE.sub("", t)
    return WS_RE.sub(" ", t).strip()


def normalize_title(title: str | None, content_text: str | None = None) -> str:
    raw = title or ""
    if not raw and content_text:
        raw = clean_entry_markers(content_text).split("。")[0]
    raw = clean_entry_markers(raw)
    raw = SUPPLEMENT_RE.sub("", raw).strip()
    return WS_RE.sub(" ", raw).strip()


def memory_num(memory_id: str) -> int:
    m = re.match(r"^mem_kb_(\d+)$", memory_id)
    return int(m.group(1)) if m else 10**9


def is_special_memory(row: dict[str, Any]) -> bool:
    mid = row.get("memory_id") or ""
    if mid.startswith("mem_priv_"):
        return True
    if row.get("status", "active") != "active":
        return True
    if row.get("user_id") not in (None, "usr_corpus_shared"):
        return True
    return False


def topic_id_for(canonical_memory_id: str, title: str) -> str:
    """Stable topic id anchored on canonical memory_id (+ short title hash)."""
    base = canonical_memory_id.replace("mem_", "topic_", 1)
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:6]
    return f"{base}_{digest}"


def golds_of(query: dict[str, Any]) -> list[str]:
    return list((query.get("expected") or {}).get("gold_memory_ids") or [])


def set_golds(query: dict[str, Any], golds: list[str]) -> None:
    expected = dict(query.get("expected") or {})
    expected["gold_memory_ids"] = golds
    query["expected"] = expected
