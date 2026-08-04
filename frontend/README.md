# OS Agent Memory Streamlit MVP

这是 OS Agent Memory 的第一版演示界面。界面使用 Streamlit 构建，只通过
FastAPI HTTP 接口访问后端，不导入数据库、ORM、Repository、算法模块或
Kylin SDK。

## 功能

- 系统状态：`GET /api/v1/health`
- 记忆导入：`POST /api/v1/events/ingest`
- 记忆搜索：`POST /api/v1/memory/search`
- 遗忘预览：`POST /api/v1/forget/preview`
- 确认遗忘：`POST /api/v1/forget/execute`
- 统一展示错误提示、HTTP 状态、`request_id`、耗时和 degraded 状态
- 在当前浏览器会话中保留用户 ID、搜索结果、memory_id 和遗忘计划

## 目录

```text
frontend/
├── streamlit_app.py          # 页面路由和公共侧栏
├── requirements.txt
├── .streamlit/config.toml
└── src/
    ├── api/client.py         # 唯一后端访问入口
    ├── components/common.py  # 响应、错误和会话状态组件
    ├── pages/                # 状态、导入、搜索、遗忘页面
    └── types/models.py       # 前端响应类型
```

## 安装

在项目根目录执行：

```powershell
python -m pip install -r frontend/requirements.txt
```

## 启动

终端一启动 FastAPI：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

终端二启动 Streamlit：

```powershell
python -m streamlit run frontend/streamlit_app.py --server.port 8501
```

浏览器打开 `http://127.0.0.1:8501`。默认 API 地址是
`http://127.0.0.1:8000/api/v1`，也可在侧栏修改，或在启动前设置：

```powershell
$env:OS_AGENT_MEMORY_API_URL = "http://127.0.0.1:8000/api/v1"
```

## 推荐演示流程

1. 在“系统状态”确认后端可用。
2. 在“记忆导入”提交一条记忆并记录生成的 `memory_id`。
3. 在“记忆搜索”使用同一个 `user_id` 搜索。
4. 在“记忆遗忘”选择搜索结果，生成预览并确认执行。
5. 再次搜索，确认已遗忘记录不再返回。

## 错误处理

连接失败、超时、非 JSON 响应、响应契约错误和所有后端错误都会显示中文提示。
后端返回的 `request_id` 会始终显示，可用于查询流程日志。可重试错误、降级模式和
降级原因会单独提示。

## 限制

- 默认 Mock 向量索引只在当前 FastAPI 应用生命周期内有效。
- Streamlit Session State 只属于当前浏览器标签页，不是持久化存储。
- 第一版不包含登录、权限管理、生产部署或复杂视觉主题。
- 真实算法、持久化向量索引与 Kylin 实机验证仍由后端阶段完成。

## 测试

```powershell
pytest frontend/tests -v
```

本项目只通过包管理器使用 Streamlit，没有复制 Streamlit 仓库源码。
