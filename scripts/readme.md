# scripts/

一键运维命令（面向 Kylin Linux 目标机；Windows 开发环境请直接运行等价 python 命令）。

| 脚本 | 作用 |
|------|------|
| `setup.sh` | 创建 venv 并安装运行/测试/前端依赖 |
| `start.sh` | 以 `algorithm_modules` profile 启动 FastAPI（可 `HOST/PORT/OS_AGENT_ENV` 覆盖） |
| `test.sh` | 全量测试（后端 + 前端） |
| `run_evaluation.sh` | 运行 Dataset V0.1 评测，报告写入 `evaluation/reports/` |
| `init_db.sh` | 初始化配置的 SQLite 数据库与 ORM 表 |
| `check_kylin_env.sh` | 麒麟实机前置检查（CPython 3.12 / 依赖 / 可选组件 / 健康检查） |

Windows 等价命令：

```powershell
# 启动（算法适配图）
$env:OS_AGENT_ENV = "algorithm_modules"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 测试
python -m pytest -q
python -m pytest frontend/tests -q

# 评测
python -m evaluation.run_all --split dev

# 初始化数据库
python -m scripts.init_db
```
