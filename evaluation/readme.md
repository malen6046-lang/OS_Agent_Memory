六、evaluation/
作用

存放自动评测程序。

建议：

evaluation/
├── __init__.py
├── run_all.py
├── preference_eval.py
├── retrieval_eval.py
├── conflict_eval.py
├── security_eval.py
├── forget_eval.py
├── latency_eval.py
└── reports/

负责人：

你主负责。

算法负责人负责提供指标所需输出，并协助分析错误案例。

最终至少计算：

偏好提取准确率
知识检索 Recall@K
冲突分类正确率
敏感信息识别准确率
遗忘正确率
平均延迟
P95 延迟