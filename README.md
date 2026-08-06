# OS Agent Memory - MVP Integrated Version

面向麒麟桌面操作系统 V11（Kylin Linux Desktop V11）的 OS Agent 记忆服务 MVP。
本仓库是四个成员分支（主项目 / Algorithm-V1.1 / memory_demo / evaluation-dataset）的集成基线，工作分支：`integration/mvp-v0.1`。

## 1. 四大组成

| 模块 | 目录 | 来源 | 说明 |
|------|------|------|------|
| 前端 | `frontend/` | 主项目 | Streamlit 界面，仅通过 FastAPI HTTP 接口访问后端，不导入后端内部实现 |
| 后端 | `app/` `contracts/` `repositories/` `migrations/` | 主项目 + memory_demo | FastAPI、Orchestrator、冻结 contracts、SQLite Repository |
| 算法 | `modules/` `adapters/` | Algorithm-V1.1 | 偏好/安全/遗忘/知识/检索算法，通过 Adapter 接入（原始源码锁定在 `modules/*/algorithm_v1_1/`） |
| 测试数据 | `evaluation/dataset/` | evaluation-dataset | 282 条 JSONL 评测用例（偏好/检索/冲突/遗忘/安全）+ 评测脚本 |

架构链路：`API → Orchestrator → 冻结 contracts Protocol → Adapter → Algorithm V1.1 → Repository/VectorStore`（V1.2.2 唯一合法链路）。

## 2. 环境要求

- CPython **3.12.x**（V1.2.1 基线：>=3.12,<3.13）
- Windows / Linux / 麒麟桌面均可运行（Kylin 实机另需平台 SDK）

## 3. 安装

```powershell
pip install -r requirements.txt
```

或使用 pyproject（等价，含测试与前端 extras）：

```powershell
python -m pip install -e ".[test,frontend]"
```

> 可选真实机依赖（MVP 演示不需要）：`sentence-transformers` / `faiss-cpu`（见 `requirements.txt` 注释）。

## 4. 启动

### 4.1 后端（终端一）

```powershell
cd <仓库根目录>
$env:OS_AGENT_ENV = "algorithm_modules"   # 完整算法适配图
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

验证：浏览器打开 `http://127.0.0.1:8000/api/v1/health`，返回 `{"status":"ok"}`。

### 4.2 前端（终端二）

```powershell
python -m streamlit run frontend/streamlit_app.py --server.port 8501
```

浏览器打开 `http://127.0.0.1:8501`（侧栏 FastAPI 地址默认 `http://127.0.0.1:8000/api/v1`）。

## 5. 演示流程

1. **系统状态**页 → 刷新 → 确认后端可用
2. **记忆导入**页 → 输入用户 ID + 内容（如 `我喜欢深色主题，并使用 Python。`）→ 导入 → 记下 memory_id
3. **记忆搜索**页 → 查询（如 `深色主题`）→ 应命中
4. **记忆遗忘**页 → 选择 memory_id → 预览 → 确认执行
5. 再次搜索 → 应无结果

## 6. 测试

```powershell
python -m pytest -q                  # 后端 + 评测单测（310 个）
python -m pytest frontend/tests -q   # 前端（34 个）
```

> pytest 已配置项目内 basetemp（`pyproject.toml`），默认即可运行。

## 7. 评测

```powershell
python -m evaluation.run_all --split dev   # dev | held_out | all
```

报告写入 `evaluation/reports/`（`v0.1_<split>.txt` / `evaluation_report.md` / `result.csv`）。
当前分数为 **baseline**（`status=baseline_not_competition_claim`）；给评测注入真实 Adapter 的方法见 `evaluation/联调注入说明.md`。

## 8. 配置 Profile

| Profile | 说明 |
|---------|------|
| `default` | 全 Mock，最轻量 |
| `development` | sentence_transformer + faiss + SQLite Repository（需可选依赖） |
| `algorithm_modules` | 完整算法适配图（推荐 MVP 演示） |
| `kylin` | 麒麟实机（需平台 SDK） |

## 9. 验收与文档

- 验收清单：`docs/MVP验收清单.md`
- 冻结规范：`docs/change_requests/CR-20260803-001~003`
- 数据集规范：`evaluation/dataset/README.md`
- 运维脚本：`scripts/`（setup / start / test / run_evaluation / init_db / check_kylin_env）
