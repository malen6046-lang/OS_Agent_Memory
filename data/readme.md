十、data/
作用

运行时数据目录。

建议：

data/
├── .gitkeep
├── sqlite/
├── vectors/
├── indexes/
├── logs/
└── reports/

负责人：

你管理目录规则，各模块通过配置使用。

不要把真实运行数据库提交到 Git。