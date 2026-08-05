"""安全检测评测 — 敏感信息识别准确率.

Usage:
    python -m evaluation.security_eval
"""
import json
from modules.preference_safety.safety_service import SafetyService
from evaluation.data_loader import load_dataset

# 数据集从文件读取（可替换 datasets/security/cases.json 更换评测集）
SECURITY_CASES = [
    (c["text"], c["sensitive"])
    for c in load_dataset("security/cases.json")
]


def evaluate_security() -> dict:
    ss = SafetyService()
    correct = 0
    total = len(SECURITY_CASES)
    for text, expect_sensitive in SECURITY_CASES:
        r = ss.check(text)
        if r["has_sensitive"] == expect_sensitive:
            correct += 1
    return {
        "dataset": {"security_cases": total},
        "sensitive_detection_accuracy": f"{correct}/{total} = {correct/total*100:.1f}%",
    }


def main():
    print(json.dumps(evaluate_security(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
