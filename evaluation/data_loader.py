"""数据集加载辅助 — 从 datasets/ 目录读取评测数据.

Usage:
    from evaluation.data_loader import load_dataset
    data = load_dataset("retrieval/queries.json")
"""
import json
import os
from typing import Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATASET_DIR = os.path.join(_PROJECT_ROOT, "datasets")


def load_dataset(rel_path: str) -> Any:
    """Load a dataset file. rel_path like 'retrieval/queries.json'."""
    full = os.path.join(_DATASET_DIR, rel_path)
    if not os.path.isfile(full):
        raise FileNotFoundError(f"dataset not found: {full}")
    with open(full, "r", encoding="utf-8") as f:
        return json.load(f)
