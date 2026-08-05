"""全部评测汇总入口.

Usage:
    python -m evaluation.run_all
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.retrieval_eval import evaluate_retrieval
from evaluation.conflict_eval import evaluate_conflict
from evaluation.preference_eval import evaluate_preference
from evaluation.security_eval import evaluate_security
from evaluation.forget_eval import evaluate_forget
from evaluation.latency_eval import evaluate_latency


def run_all() -> dict:
    report = {
        "retrieval": evaluate_retrieval(),
        "conflict": evaluate_conflict(),
        "preference": evaluate_preference(),
        "security": evaluate_security(),
        "forget": evaluate_forget(),
        "latency": evaluate_latency(),
    }
    return report


def main():
    print(json.dumps(run_all(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
