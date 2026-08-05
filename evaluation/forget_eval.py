"""遗忘评测 — 精准遗忘正确率（目标内容被删，无关内容保留）.

Usage:
    python -m evaluation.forget_eval
"""
import json
from modules.preference_safety.forget_service import ForgetService
from evaluation.data_loader import load_dataset

# 数据集从文件读取（可替换 datasets/forget/cases.json 更换评测集）
CASES = [
    (c["instruction"], c["keyword"])
    for c in load_dataset("forget/cases.json")
]


def evaluate_forget() -> dict:
    fs = ForgetService()
    preview_correct = 0
    for instruction, exp_kw in CASES:
        plan = fs.preview(instruction)
        kw = plan["keyword"]
        if exp_kw == "全部":
            if plan["scope"] == "all" and kw == "全部":
                preview_correct += 1
        elif kw == exp_kw:
            preview_correct += 1

    # 执行: token 有效性 + 用户隔离
    fs2 = ForgetService()
    plan = fs2.preview("\u5fd8\u8bb0\u4e3b\u9898", user_id="usr_A")
    unauthorized = fs2.execute(plan["confirmation_token"], user_id="usr_B")
    authorized = fs2.execute(plan["confirmation_token"], user_id="usr_A")
    isolation_ok = unauthorized["success"] is False and authorized["success"] is True

    return {
        "dataset": {"forget_cases": len(CASES)},
        "keyword_extraction_accuracy": f"{preview_correct}/{len(CASES)} = {preview_correct/len(CASES)*100:.1f}%",
        "user_isolation": "pass" if isolation_ok else "fail",
    }


def main():
    print(json.dumps(evaluate_forget(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
