八、configs/
作用

保存非敏感配置。

建议：

configs/
├── default.yaml
├── development.yaml
├── kylin.yaml
└── test.yaml

负责人：

你。

规则：

不放数据库密钥；
不放个人绝对路径；
不放用户名；
不硬编码向量维度；
密钥使用环境变量。