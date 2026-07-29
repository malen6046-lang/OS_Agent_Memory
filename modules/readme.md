三、modules/
作用

存放两个业务模块的真正实现。

建议：

modules/
├── preference_safety/
└── knowledge_retrieval/
modules/preference_safety/

作用：

多源清洗；
偏好提取；
偏好合并；
偏好版本更新；
敏感信息识别；
遗忘指令解析；
生成遗忘预览。

负责人：

偏好与安全负责人。

该负责人只能实现 contracts/protocols/ 已定义的接口。

modules/knowledge_retrieval/

作用：

知识结构化；
Embedding；
BM25；
向量检索；
混合排序；
冲突分类；
记忆流转。

负责人：

算法负责人。

注意：麒麟 SDK 的具体包装更适合放在 adapters/，算法模块只调用适配器接口。