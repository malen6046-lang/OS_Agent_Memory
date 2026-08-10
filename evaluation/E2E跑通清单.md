# 5 个精品 E2E 跑通清单

**依据**：`4号下周安排建议.docx` 第五项  
**目标**：先做到 5 个精品场景完全跑通（不用 20 个）  
**标准链路**：

```text
单一 user_id → 输入 → 记忆形成 → 检索 → 更新/冲突 → 遗忘 → 结果验证
```

## 数据层就绪（4号）

| 场景 | user_id | 数据层 | 实机联调 | 说明 |
|------|---------|--------|----------|------|
| SCN-01 开发助手 | `usr_kylin_004` | ✅ | dataset_gold_ok_e2e_pending | 引用齐全 / 用户隔离 OK |
| SCN-02 办公助手 | `usr_kylin_005` | ✅ | dataset_gold_ok_e2e_pending | 引用齐全 / 用户隔离 OK |
| SCN-03 系统维护助手 | `usr_kylin_003` | ✅ | dataset_gold_ok_e2e_pending | 引用齐全 / 用户隔离 OK |
| SCN-04 知识问答 | `usr_corpus_shared` | ✅ | baseline_retrieval_only | 引用齐全 / 用户隔离 OK |
| SCN-05 遗忘操作 | `usr_kylin_003` | ✅ | in_memory_forget_ok_real_db_pending | 引用齐全 / 用户隔离 OK |

## 每场景必跑检查（1/2号联调时勾选）

对每个 SCN-01…05：

- [ ] 全程只有剧本中的单一 `user_id`
- [ ] 初次输入能写入/抽取记忆（偏好或知识）
- [ ] 第二次调用能检索到预期记忆
- [ ] 若有冲突：relation/strategy 与 GT 一致
- [ ] 若有遗忘：delete/keep 与 GT 一致，且未 DropCollection
- [ ] 结果与场景文档「预期结果」一致；填写「联调回填」

## 场景文件

| ID | 文档 |
|----|------|
| SCN-01 | [`scenarios/01_开发助手.md`](./scenarios/01_开发助手.md) |
| SCN-02 | [`scenarios/02_办公助手.md`](./scenarios/02_办公助手.md) |
| SCN-03 | [`scenarios/03_系统维护助手.md`](./scenarios/03_系统维护助手.md) |
| SCN-04 | [`scenarios/04_知识问答.md`](./scenarios/04_知识问答.md) |
| SCN-05 | [`scenarios/05_遗忘操作.md`](./scenarios/05_遗忘操作.md) |

## 联调入口

见 [`联调注入说明.md`](./联调注入说明.md)。注入服务后：

```bash
python -m evaluation.run_all --split dev
python -m evaluation.collect_failures --split dev
python -m evaluation.check_scenario_user_consistency
python -m evaluation.check_e2e_ready
```

联调完成后更新各场景 md 末尾「联调回填」，并改 `scenarios.json` 的 `actual_result_status`。
