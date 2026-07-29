1. app/
作用

这是整个系统的“总控制中心”。

它负责：

启动 FastAPI；
接收外部 API 请求；
调用不同模块；
返回统一格式；
管理依赖注入；
管理系统启动和关闭；
组合偏好、安全、检索和数据库模块。
负责人

你：项目负责人。

系统后端负责人可以协助编写 API，但最终目录结构和调用关系由你管理。

建议结构：

app/
├── __init__.py
├── main.py
├── api/
├── core/
├── orchestrator/
└── dependencies/

FastAPI 官方也建议将较大的项目拆分到多个模块和 APIRouter 中，而不是把所有接口放进一个文件。

文件说明
app/__init__.py

作用：

标记 app 是 Python 包；
通常保持空文件。

负责人：你

app/main.py

作用：

创建 FastAPI 应用；
注册所有路由；
注册异常处理；
管理启动和关闭生命周期；
提供程序入口。

最终大致会是：

from fastapi import FastAPI

app = FastAPI(
    title="OS Agent Memory System",
    version="1.0.0",
)

负责人：你

后端负责人协助。

app/api/

作用：

存放 REST API 路由，例如：

app/api/
├── __init__.py
└── v1/
    ├── __init__.py
    ├── events.py
    ├── preferences.py
    ├── knowledge.py
    ├── memory.py
    ├── conflicts.py
    ├── forget.py
    ├── evaluations.py
    └── health.py

职责划分：

文件	内容	主要负责人
events.py	多源事件接入	你／后端负责人
preferences.py	偏好提取和查询 API	后端负责人
knowledge.py	知识写入 API	后端负责人
memory.py	检索和记忆流转 API	后端负责人
conflicts.py	冲突处理 API	后端负责人
forget.py	遗忘预览和执行 API	后端负责人／你
evaluations.py	启动评测	你
health.py	健康检查	你／后端负责人

注意：

API 文件只负责接收参数和返回响应，不能在里面直接写算法、SQL 或调用麒麟 SDK。

app/core/

作用：

保存全项目都要使用的基础设施。

建议包含：

app/core/
├── __init__.py
├── config.py
├── errors.py
├── responses.py
├── logging.py
├── ids.py
└── security.py
文件	作用	负责人
config.py	读取 YAML、环境变量	你
errors.py	统一错误码和异常类	你
responses.py	成功、失败响应格式	你
logging.py	日志格式与 request_id	你
ids.py	生成 mem_、req_ 等 ID	你
security.py	密钥读取、基础安全配置	你

这里不是算法负责人所说的“敏感信息识别模块”；这里只放系统级安全工具。

app/orchestrator/

作用：

这是整个项目最核心的“调度中心”。

建议：

app/orchestrator/
├── __init__.py
└── memory_orchestrator.py

MemoryOrchestrator 负责组合：

事件接入
→ 安全预检查
→ 偏好提取
→ 知识写入
→ 向量检索
→ 冲突判断
→ 遗忘执行
→ 审计记录

负责人：你

它不能自己实现具体算法，而是调用接口：

self.preference_service.extract(...)
self.knowledge_service.ingest(...)
self.retriever.search(...)
app/dependencies/

作用：

集中创建和提供服务实例。

例如：

app/dependencies/
├── __init__.py
├── services.py
└── database.py

它负责决定当前使用：

MockPreferenceService
还是
RealPreferenceService

以及使用：

KylinEmbeddingProvider
还是
FallbackEmbeddingProvider

负责人：你／后端负责人