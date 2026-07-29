五、migrations/
作用

管理 SQLite 数据库表结构变化。

建议：

migrations/
├── README.md
├── versions/
└── init.sql

第一版可以先使用 SQLAlchemy 自动建表，但仍要保留明确初始化和升级方式。

负责人：

系统后端负责人。

算法负责人不直接修改数据库迁移。