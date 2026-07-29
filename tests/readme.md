七、tests/
作用

确保不同成员的模块能够真正接起来。

建议：

tests/
├── contract/
├── unit/
├── integration/
└── smoke/
tests/contract/

作用：

验证 Schema 和 Protocol 有没有被破坏。

负责人：

你。

这是最重要的公共测试。

tests/unit/

作用：

测试单个类或函数。

负责人：

各自负责自己的代码。

tests/unit/platform/        你
tests/unit/preference/      偏好与安全负责人
tests/unit/retrieval/       算法负责人
tests/unit/backend/         系统后端负责人
tests/integration/

作用：

测试多个模块组合。

例如：

API → Orchestrator → Mock Service → SQLite

负责人：

系统后端负责人。

tests/smoke/

作用：

测试系统最基本功能：

能否启动；
健康检查是否正常；
数据库是否能连接；
Mock 模块是否能调用。

负责人：

你。