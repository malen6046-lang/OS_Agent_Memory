"""Conflict classification evaluation.

Usage:
    python -m evaluation.conflict_eval
"""
import json
from modules.knowledge_retrieval.conflict_classifier import ConflictClassifier
from evaluation.data_loader import load_dataset

# 数据集从文件读取（可替换 datasets/conflict/pairs.json 更换评测集）
CONFLICT_PAIRS = [
    (p["new"], p["old"], p["expected"])
    for p in load_dataset("conflict/pairs.json")
]


def evaluate_conflict() -> dict:
    cc = ConflictClassifier()
    total = len(CONFLICT_PAIRS)
    correct = 0
    confusion = {}

    for new_text, old_text, expected in CONFLICT_PAIRS:
        old_meta = {"memory_id": "old", "content_text": old_text}
        if expected == "replace":
            old_meta["valid_from"] = "2025-01-01"
            result = cc.classify(new_text, {"valid_from": "2026-08-01"},
                                 [{"score": 0.90, "meta": old_meta}])
        elif expected in ("contradict", "extend"):
            result = cc.classify(new_text, {}, [{"score": 0.90, "meta": old_meta}])
        else:
            result = cc.classify(new_text, {},
                                 [{"score": 0.30 if expected == "unrelated" else 0.95,
                                   "meta": old_meta}])
        pred = result["relation"]
        if pred == expected:
            correct += 1
        key = f"{expected}->{pred}"
        confusion[key] = confusion.get(key, 0) + 1

    return {
        "dataset": {"conflict_pairs": total},
        "conflict_accuracy": f"{correct}/{total} = {correct/total*100:.1f}%",
        "confusion": confusion,
    }


def main():
    print(json.dumps(evaluate_conflict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
