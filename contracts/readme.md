二、contracts/
作用

这是三人开发中最重要的目录。

它相当于：

三个人共同使用的插头标准。

其中的字段、接口和枚举一旦确定，其他成员不得自行修改。

负责人：你维护，三人共同遵守。

建议结构：

contracts/
├── __init__.py
├── schemas/
├── protocols/
├── examples/
└── CHANGELOG.md
contracts/schemas/

作用：

用 Pydantic 定义所有跨模块数据对象。

Pydantic 模型可以同时用于数据验证、序列化和 JSON Schema 生成，适合将 V1.1 文档中的字段真正固化为代码。

建议文件：

contracts/schemas/
├── __init__.py
├── common.py
├── envelope.py
├── memory.py
├── preference.py
├── knowledge.py
├── retrieval.py
├── forget.py
├── provider.py
├── evaluation.py
└── responses.py
文件	主要内容	负责人
common.py	公共枚举、通用类型	你
envelope.py	多源数据 Envelope	你
memory.py	MemoryRecord	你
preference.py	PreferenceRecord、Candidate	你先定义，算法负责人复核
knowledge.py	KnowledgeRecord、ConflictDecision	你先定义，算法负责人复核
retrieval.py	SearchRequest、SearchResponse	你先定义，算法负责人复核
forget.py	ForgetPreview、Plan、Execute	你先定义，偏好安全负责人复核
provider.py	Embedding、VectorStore 数据结构	你先定义，算法负责人复核
evaluation.py	指标和评测结果	你
responses.py	统一 API 响应	你

“复核”不等于让成员自行修改字段。成员发现问题后通过 PR 提交建议。

contracts/protocols/

作用：

定义模块必须实现的方法。

建议：

contracts/protocols/
├── __init__.py
├── preference.py
├── knowledge.py
├── retrieval.py
├── embedding.py
├── vector_store.py
├── safety.py
└── forget.py
文件	接口	主要实现负责人
preference.py	PreferenceService	偏好与安全负责人
knowledge.py	KnowledgeService	算法负责人
retrieval.py	HybridRetriever	算法负责人
embedding.py	EmbeddingProvider	算法负责人
vector_store.py	VectorStoreAdapter	算法负责人
safety.py	SafetyService	偏好与安全负责人
forget.py	ForgetService	偏好与安全负责人

接口文件由你创建和冻结，具体实现由对应负责人完成。

contracts/examples/

作用：

存放标准输入输出示例。

例如：

contracts/examples/
├── envelope.json
├── memory_record.json
├── preference_record.json
├── search_request.json
├── search_response.json
├── forget_preview.json
└── error_response.json

这些文件非常重要，因为队友拿去问 AI 时，可以明确告诉 AI：

输出必须与这个示例一致。

负责人：你

contracts/CHANGELOG.md

作用：

记录接口契约修改。

例如：

## 1.0.0
- 初始契约
- 新增 Envelope
- 新增 MemoryRecord
- 新增 PreferenceRecord

负责人：你

只有公共字段发生 breaking change 时才升级主版本。

