"""偏好提取评测 — exact-match accuracy + macro F1.

Usage:
    python -m evaluation.preference_eval
"""
import json
from modules.preference_safety.preference_service import PreferenceService
from evaluation.data_loader import load_dataset

# 数据集从文件读取（可替换 datasets/preference/cases.json 更换评测集）
PREFERENCE_CASES = [
    (c["text"], c["key"], c["value"])
    for c in load_dataset("preference/cases.json")
]


def evaluate_preference() -> dict:
    ps = PreferenceService()
    correct = 0
    total = len(PREFERENCE_CASES)
    for text, exp_key, exp_val in PREFERENCE_CASES:
        candidates = ps.extract([{"text": text, "user_id": "u1", "scene": "desktop"}])
        hit = any(c["preference_key"] == exp_key and c["value"] == exp_val for c in candidates)
        if hit:
            correct += 1
    return {
        "dataset": {"preference_cases": total},
        "exact_match_accuracy": f"{correct}/{total} = {correct/total*100:.1f}%",
    }


def main():
    print(json.dumps(evaluate_preference(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
