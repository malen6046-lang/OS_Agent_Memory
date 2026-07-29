四、adapters/
作用

把外部 SDK 或开源项目转换成本项目统一接口。

建议：

adapters/
├── embedding/
└── vector_store/
adapters/embedding/

建议包含：

adapters/embedding/
├── __init__.py
├── kylin_provider/
├── fallback_provider.py
└── mock_provider.py

作用：

kylin_provider/：调用麒麟 Embedding C/C++ SDK；
fallback_provider.py：普通 Linux 环境本地向量化；
mock_provider.py：测试时返回固定向量。

负责人：

算法负责人主写，你负责审核配置和集成。

adapters/vector_store/

建议包含：

adapters/vector_store/
├── __init__.py
├── kylin_vector_store/
├── faiss_vector_store.py
└── memory_vector_store.py

作用：

麒麟向量数据库适配；
FAISS fallback；
内存版测试适配器。

负责人：

算法负责人主写，你负责映射表和删除事务集成。

V1.1 要求业务层不能直接调用麒麟 SDK，必须经过 EmbeddingProvider 和 VectorStoreAdapter。