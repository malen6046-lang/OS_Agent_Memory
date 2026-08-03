十一、根目录文件
THIRD_PARTY.md

作用：

记录引入的 GitHub 仓库和 SDK：

仓库名称
GitHub 地址
Commit
License
使用文件
修改内容
负责人

负责人：

你维护，每个成员负责填写自己引入的项目。

pyproject.toml

作用：

统一：

Python 版本；
项目名称；
Python 依赖；
pytest 配置；
lint 配置；
格式化规则。

负责人：

你／系统后端负责人。

README.md

作用：

告诉任何新成员：

项目是什么；
如何安装；
如何启动；
如何测试；
如何切换 fallback 和麒麟模式；
项目目录是什么；
已知问题有哪些。

负责人：

你。

## FastAPI

- Repository: https://github.com/fastapi/fastapi
- Usage: REST API framework and OpenAPI generation
- Integration type: Runtime dependency
- Modified source: No
- Project location: app/main.py, app/api/
- Maintainer: 平台与集成负责人

## Pydantic

- Repository: https://github.com/pydantic/pydantic
- Usage: Contract validation and serialization
- Integration type: Runtime dependency
- Modified source: No
- Project location: contracts/schemas/
- Maintainer: 平台与集成负责人

## Streamlit

- Version: 1.37.1
- Repository: https://github.com/streamlit/streamlit
- License: Apache-2.0
- Usage: OS Agent Memory MVP interactive frontend
- Integration type: Frontend runtime dependency installed by package manager
- Modified source: No
- Project location: frontend/
- Maintainer: project maintainer / platform integration

## HTTPX

- Version: 0.27.0
- Repository: https://github.com/encode/httpx
- License: BSD-3-Clause
- Usage: Frontend-to-FastAPI HTTP client
- Integration type: Frontend runtime dependency installed by package manager
- Modified source: No
- Project location: frontend/src/api/client.py
- Maintainer: project maintainer / platform integration

## Uvicorn

- Version: 0.51.0
- Repository: https://github.com/Kludex/uvicorn
- License: BSD-3-Clause
- Usage: ASGI server for running the existing FastAPI backend during the MVP demo
- Integration type: Demo runtime dependency installed by package manager
- Modified source: No
- Project location: frontend/requirements.txt
- Maintainer: project maintainer / platform integration

## SQLAlchemy

- Repository: https://github.com/sqlalchemy/sqlalchemy
- Usage: SQLite ORM and transaction management
- Integration type: Runtime dependency
- Modified source: No
- Project location: app/models/, app/repositories/
- Maintainer: 平台与集成负责人
