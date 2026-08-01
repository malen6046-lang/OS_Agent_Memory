# 算法模块 README

## 目录结构

```
modules/
├── knowledge_retrieval/        # 模块 B：知识检索与记忆
│   ├── bm25.py                 #   中文分词 + BM25 关键词检索
│   ├── hybrid_retriever.py     #   Dense向量 + BM25 → RRF 融合排序
│   ├── knowledge_service.py    #   知识写入 + 冲突检测 + 冲突策略
│   ├── conflict_classifier.py  #   六分类冲突判定器
│   ├── memory_tier.py          #   三层记忆流转 (短期→中期→长期)
│   └── service_factory.py      #   服务工厂 (供平台容器调用)
└── preference_safety/          # 模块 A：偏好与安全
    ├── preference_service.py   #   偏好提取 (100条规则引擎)
    ├── safety_service.py       #   PII 检测 (手机号/身份证/邮箱等)
    └── forget_service.py       #   自然语言遗忘 (两阶段 preview+execute)
```

## 测试

```bash
# 模块 B：知识检索
pytest tests/unit/retrieval/ -v

# 模块 A：偏好与安全
pytest tests/unit/preference_safety/ -v

# 全部算法测试
pytest tests/unit/retrieval/ tests/unit/preference_safety/ -v
```

## 端到端演示

```bash
python examples/retrieval_demo.py
```

## 检索链路

```
查询 → EmbeddingProvider.encode() → 向量
    → VectorStoreAdapter.query() → 余弦 top-30
    → BM25Retriever.search() → 关键词 top-30
    → HybridRetriever._rrf() → RRF 融合
    → {items: [{memory_id, score, memory_kind, content_text, metadata}]}
```

向量不可用时自动降级 BM25，meta 标注 degraded=true。

## 冲突处理

六分类：duplicate(保留旧的) / contradict(人工审核) / replace(保留新的) / extend(合并) / support(合并) / unrelated(各自保留)

## 三层记忆流转

Working(60s半衰) → Episodic(3600s半衰) → Semantic(永久)
提升条件: access≥3 + importance≥0.5
衰减公式: strength = exp(-ln(2) × age / half_life)

## 偏好提取

100 条规则引擎，4 个类别：ui(20) / tool(30) / security(25) / workflow(25)

## 安全检测

手机号 / 身份证 / 银行卡 / 邮箱 / API Key / 密码 / 敏感关键词

## 遗忘流程

preview → 解析自然语言 → 关键词 → 候选ID → confirmation_token
execute → 验证token → tombstone → 向量删除 → 返回结果

## Provider 切换

```python
# Mock (测试用)
from adapters.embedding.mock_provider import MockEmbeddingProvider
# Fallback (需要 sentence-transformers)
from adapters.embedding.fallback_provider import FallbackEmbeddingProvider
# Kylin (麒麟真机)
# from adapters.embedding.kylin_provider import KylinEmbeddingProvider
```

## 已知问题

- KylinEmbeddingProvider / KylinVectorStoreAdapter 待麒麟目标机
- FAISS 实验版，未进入 MVP
- MemoryTier 纯内存，重启丢失

## 评测局限性（诚实声明）

- 冲突分类使用字符规则：否定词、通用反义词、时间戳优先级、
  字符重叠门槛、槽位冲突检测（最长公共前后缀 + 中间取值不同判矛盾）。
  在自建小样本上表现良好，但**未经独立数据集验证**；
  真实成绩必须以大赛数据集和真模型（BGE/Kylin）实测为准。
- 检索评测使用 Mock 向量（sha256 生成），不携带真实语义；
  Recall@5 主要依赖 BM25 关键词匹配，不能用真实模型成绩替代。
  真实 BGE 模型评测见 evaluation/run_real_eval.py。
- 遗忘关键词解析为规则引擎，标准样本准确率约 80%；
  复杂自然语言变体（"把X都忘了吧"等）覆盖有限，
  需 LLM 或语义解析才能突破 85% 目标。
- 当前所有指标均为开发期基线，不构成最终比赛成绩。
