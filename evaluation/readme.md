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

空的 `*_eval.py` 已填入 **Dataset V0.1 数据 + 可运行评测**。  
数据在对应文件的 `CASES`（检索另有 `CORPUS`），为 **Python 字典列表**

| 文件 | 数据 | 条数 |
|------|------|------|
| `preference_eval.py` | `CASES` | 50 |
| `retrieval_eval.py` | `CORPUS` + `CASES` | 50+50 |
| `conflict_eval.py` | `CASES` | 20 |
| `forget_eval.py` | `CASES` | 20 |
| `security_eval.py` | `CASES` | 10 |
| `latency_eval.py` | 复用 retrieval | — |
| `run_all.py` | 汇总入口 | — |

运行环境（冻结基线）：**仅 CPython 3.12.x**，评测脚本与 `reports` 均为 Python 产出，无其它编程语言。

```bash
cd OS_Agent_Memory-main
python3.12 -m evaluation.run_all --split dev
python3.12 -m evaluation.conflict_eval --split all
```

```python
from evaluation.conflict_eval import CASES
from evaluation.retrieval_eval import CORPUS, CASES as QUERIES
```

格式参考：LaMP / BEIR / SNLI·MNLI / TOFU；样本为银河麒麟原创场景。
