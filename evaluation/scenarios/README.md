# 端到端场景集（Dataset V0.1）

**要求来源**：8_3 / 8_4 审核及安排 —— 开发助手 / 办公助手 / 系统维护 / 知识问答 / 遗忘操作  
**写法**：每个场景必须写清  
`初次输入 → 产生记忆 → 第二次调用 → 预期结果 → 实际结果`  
**用户隔离（8_4 P1）**：每个场景固定一个 `user_id`；私有用例不得跨用户拼接；公共知识须标明 `usr_corpus_shared`。  
**检查脚本**：[`../check_scenario_user_consistency.py`](../check_scenario_user_consistency.py)  
**机器可读索引**：[`scenarios.json`](./scenarios.json)

| ID | 场景 | user_id | 主文件 |
|----|------|---------|--------|
| SCN-01 | 开发助手 | `usr_kylin_004` | [01_开发助手.md](./01_开发助手.md) |
| SCN-02 | 办公助手 | `usr_kylin_005` | [02_办公助手.md](./02_办公助手.md) |
| SCN-03 | 系统维护助手 | `usr_kylin_003` | [03_系统维护助手.md](./03_系统维护助手.md) |
| SCN-04 | 知识问答 | `usr_corpus_shared`（公共知识空间） | [04_知识问答.md](./04_知识问答.md) |
| SCN-05 | 遗忘操作 | `usr_kylin_003` | [05_遗忘操作.md](./05_遗忘操作.md) |

**关于「实际结果」**：当前按 Dataset 金标 + baseline 口径填写；接入实服务后在「联调回填」更新。场景设计 ≠ 真实端到端完成。
