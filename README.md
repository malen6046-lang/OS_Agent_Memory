# OS Agent Memory

面向麒麟桌面系统的端侧 Agent 记忆服务。后端采用 FastAPI、Pydantic V2、
SQLAlchemy 2.0 和 SQLite，并通过适配器接入知识写入、混合检索、偏好、
安全检测和自然语言遗忘算法。

## 环境

- Python 3.12
- 依赖版本以 `requirements.lock` 为准

## 安装

```cmd
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
```

## 运行测试

```cmd
.venv\Scripts\python.exe -m pytest tests -q
```

当前完整测试基线：`260 passed, 11 skipped`。跳过项仅涉及可选的
`sentence-transformers` 后备模型。

## 启动 API

```cmd
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

启动后访问：

- Swagger：<http://127.0.0.1:8000/docs>
- OpenAPI：<http://127.0.0.1:8000/openapi.json>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>

## 目录

- `app/`：FastAPI、业务服务、Repository 和 ORM
- `contracts/`：冻结的 Pydantic Schema 与协议
- `modules/`：知识检索、偏好、安全和遗忘算法
- `adapters/`：Embedding 与向量存储适配器
- `tests/`：合同、单元、持久化和 API 集成测试
- `configs/`：运行环境配置

## 项目文档

- [后端代码总览](docs/后端代码总览.md)：代码分层、接口、算法、持久化、配置和测试说明
