# -*- coding: utf-8 -*-
"""Freeze dataset into dev / validation / final_test (replace held_out).

Policy (4号下周安排建议):
- dev:         给 1/2 号看答案，开发调试
- validation:  每轮集成统一评测；本轮优化期间冻结答案
- final_test:  最终盲测；1/2 号不得提前看答案

Migration: keep existing `dev`; split former `held_out` by case_id into
validation (first half) and final_test (second half). Corpus has no split.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation" / "dataset"
MANIFEST = DATASET / "freeze_manifest.json"

TASK_FILES = [
    "preference.jsonl",
    "retrieval_queries.jsonl",
    "conflict.jsonl",
    "forget.jsonl",
    "security.jsonl",
]

VALID_SPLITS = {"dev", "validation", "final_test"}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dump_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def remap_held_out(rows: list[dict]) -> list[dict]:
    held = [r for r in rows if r.get("split") == "held_out"]
    others = [r for r in rows if r.get("split") != "held_out"]
    if not held:
        # already migrated? normalize unknown
        for r in others:
            if r.get("split") not in VALID_SPLITS and "split" in r:
                raise ValueError(f"unexpected split={r.get('split')!r} id={r.get('case_id')}")
        return rows

    held_sorted = sorted(held, key=lambda r: r.get("case_id") or "")
    mid = (len(held_sorted) + 1) // 2  # validation gets ceil half
    remap = {
        r["case_id"]: ("validation" if i < mid else "final_test")
        for i, r in enumerate(held_sorted)
    }
    out = []
    for r in rows:
        if r.get("case_id") in remap:
            r = dict(r)
            r["split"] = remap[r["case_id"]]
        out.append(r)
    return out


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_manifest(files_stats: dict) -> dict:
    frozen_ids: dict[str, dict[str, list[str]]] = {}
    content_hashes: dict[str, str] = {}
    for fname in TASK_FILES:
        path = DATASET / fname
        rows = load_jsonl(path)
        by_split: dict[str, list[str]] = {"validation": [], "final_test": []}
        frozen_lines = []
        for r in rows:
            sp = r.get("split")
            if sp in by_split:
                by_split[sp].append(r["case_id"])
                frozen_lines.append(json.dumps(r, ensure_ascii=False, sort_keys=True))
        frozen_ids[fname] = {k: sorted(v) for k, v in by_split.items()}
        content_hashes[fname] = sha256_text("\n".join(sorted(frozen_lines)))
        files_stats[fname] = dict(Counter(r.get("split") for r in rows))

    return {
        "schema_version": "0.1.0",
        "dataset_release": "V0.2-split-freeze",
        "policy": {
            "dev": "开发调试；1/2号可见答案",
            "validation": "每轮集成评测；本轮优化期间禁止改 GT/答案",
            "final_test": "最终盲测；1/2号不得提前看到答案",
        },
        "legacy_note": "原 held_out 已拆为 validation（前半）+ final_test（后半），按 case_id 排序稳定划分",
        "counts": files_stats,
        "frozen_case_ids": frozen_ids,
        "frozen_content_sha256": content_hashes,
    }


def main() -> None:
    files_stats: dict = {}
    for fname in TASK_FILES:
        path = DATASET / fname
        rows = load_jsonl(path)
        if any(r.get("split") == "held_out" for r in rows):
            rows = remap_held_out(rows)
            dump_jsonl(path, rows)
            print(f"remapped {fname}")
        else:
            print(f"skip remap {fname} (no held_out)")
        files_stats[fname] = dict(Counter(r.get("split") for r in rows))

    manifest = build_manifest(files_stats)
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("wrote", MANIFEST)
    for fname, c in files_stats.items():
        print(f"  {fname}: {c}")


if __name__ == "__main__":
    main()
