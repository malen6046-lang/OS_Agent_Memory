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

## SQLAlchemy

- Repository: https://github.com/sqlalchemy/sqlalchemy
- Usage: SQLite ORM and transaction management
- Integration type: Runtime dependency
- Modified source: No
- Project location: app/models/, app/repositories/
- Maintainer: 平台与集成负责人