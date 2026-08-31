# Dataset V0.5 说明（字段 · 标注 · 判定规则）

**项目**：XA-202612 OS Agent 记忆优化及高效应用研究  
**平台**：银河麒麟桌面 V11（x86_64）  
**契约**：模块接口规划 V1.2.1 Schema + V1.2.2 冻结规范  
**格式标准**：UTF-8 **JSONL**（一行一条 JSON 对象）  
**运行时**：CPython 3.12.x  
**版本**：0.5.0（`dataset_release=V0.5-dev-scale-820`）  
**日期**：2026-08-31  

> V0.5 将各任务扩至约 **820** 条（新增均在 **dev**）；**validation / final_test 仍冻结**。扩样脚本：`scripts/expand_dataset_to_500.py --target 820`。

---

## 1. 标准文件清单

| 文件 | 任务 | 条数 | 主指标 |
|------|------|------|--------|
| `preference.jsonl` | 偏好提取 | 820 | exact-match、micro/macro F1、临时指令误记率 |
| `knowledge_corpus.jsonl` | 知识语料（MemoryRecord） | 820 | 被检索语料 |
| `retrieval_queries.jsonl` | 知识检索 | 820 | Recall@K、MRR、延迟 |
| `conflict.jsonl` | 知识/偏好冲突 | 820 | joint_accuracy（relation+strategy） |
| `forget.jsonl` | 精准遗忘 | 820 | preview P/R、execute/残留 |
| `security.jsonl` | 敏感过滤 | 820 | block + entity_type |

**任务样本总计**：4100 条；含语料 **4920** 条。新增规模样本均落在 `dev`（validation/final_test 数量不变）。

端到端场景见 [`../scenarios/`](../scenarios/)（开发助手 / 办公助手 / 系统维护 / 知识问答 / 遗忘操作）。

P3 困难集标签含 `hard` / `p3` / `multi_gold`（≥10 条）/ `no_answer` / `cross_user` 等；语料含 inactive/tombstoned 与跨用户私有 `mem_priv_*`。

联调注入：[`../联调注入说明.md`](../联调注入说明.md)。第二人抽查：[`../第二人抽查清单.md`](../第二人抽查清单.md)。

划分：`dev` / `validation` / `final_test`（见 [`SPLIT_POLICY.md`](./SPLIT_POLICY.md)）。  
`validation` 与 `final_test` 本轮冻结；校验：`python -m evaluation.check_freeze`。  
旧名 `held_out` 已废弃（加载时等同 `validation`）。

加载入口：`evaluation.loaders.load_cases(task, split=...)`。

---

## 2. 公共字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | string | 数据集 schema，当前 `0.1.0` |
| `case_id` | string | 用例唯一 ID，如 `PREF-0001` |
| `task_type` | string | 任务类型枚举见下 |
| `split` | string | `dev` \| `validation` \| `final_test` |
| `user_id` | string | 用户隔离键 |
| `scene` | string | 场景标签（自由字符串，需麒麟相关） |
| `evaluation` | object | 主指标与附报指标声明 |
| `tags` | string[] | 检索/展示用标签 |
| `provenance` | object | `inspired_by` / `license_note` / `adaptation` |
| `quality` | object | `generation`、`human_reviewed` 等 |

`task_type` 取值：`preference_extract` | `knowledge_retrieval` | `knowledge_conflict` | `precise_forget` | `sensitive_filter`。

---

## 3. 分任务字段与标注规范

### 3.1 preference.jsonl

**输入**：`input_events[]`，每项为 V1.2.1 **Envelope**：

| 字段 | 必填 | 规则 |
|------|------|------|
| `contract_version` | 是 | `1.0` |
| `request_id` / `idempotency_key` | 是 | 非空 |
| `user_id` / `scene` / `source` / `source_event_id` / `occurred_at` | 是 | `source`∈{tool_result,user_behavior,manual_config,cross_scene} |
| `session_id` | 否 | 可 null |
| `payload.text` | 是 | 中文用户/行为描述 |

**期望**：`expected`

| 字段 | 规则 |
|------|------|
| `preferences[]` | 对齐 **PreferenceRecord**：preference_key, value, category, scope, scope_value, polarity, confidence, evidence_count, evidence, revision, status |
| `category` | ∈{operation_habit, output_style, tool_choice, safety_policy} |
| `scope` | ∈{global, scene, tool} |
| `is_ephemeral_instruction` | true 时表示临时指令 |
| `ephemeral_text` | 临时指令可选备注（非长期偏好） |

**标注判定**

1. 长期偏好：可跨会话复用的明确习惯/配置 → 写入 `preferences`。  
2. **临时指令**：含「这次/临时/仅本次」等且不应入库 → `is_ephemeral_instruction=true` 且 **`preferences` 必须为 `[]`**。  
3. Exact-match 比较字段集合：`preference_key,value,category,scope,scope_value,polarity,status`（无序集合相等）。  
4. 禁止把一次性输出格式要求标成长期偏好。

### 3.2 knowledge_corpus.jsonl

每行一条 **MemoryRecord**（`extra=forbid`，勿加 `schema_version`）：

| 字段 | 规则 |
|------|------|
| `memory_id` | 稳定 ID，检索 gold 引用它 |
| `memory_kind` | 语料主用 `semantic` |
| `subtype` | ∈{workflow,fact,template,case,...} |
| `content_text` | **非空**；与 `content` 语义一致 |
| `content` | 建议含 title/body/keywords/knowledge_type |
| `status` | 默认可检索为 `active` |
| `user_id` | 用户隔离；共享语料可用约定共享用户 |

### 3.3 retrieval_queries.jsonl

| 字段 | 规则 |
|------|------|
| `query` | 中文自然语言问题 |
| `top_k` | 如 [1,3,5,10] |
| `expected.gold_memory_ids` | **必须**存在于 corpus；**禁止**用「含关键词」代替 |
| `evaluation.match` | 固定 `memory_id` |

**判定**：`Recall@K = |TopK ∩ gold| / |gold|`（不是 Hit@K）。附报 Hit@K、MRR。检索必须带 `user_id` 过滤意识。

### 3.4 conflict.jsonl

| 字段 | 规则 |
|------|------|
| `old` / `new` | 完整 MemoryRecord |
| `expected.relation` | ∈{duplicate,support,extend,replace,contradict,unrelated} |
| `expected.strategy` | ∈{keep_old,keep_new,merge,manual_review} |
| `expected.reason_codes` | 字符串列表 |
| `expected.old_memory_id` / `new_memory_id` | 与 old/new 一致 |

**判定规则（标注口径）**

| relation | 何时标 | 常见 strategy |
|----------|--------|----------------|
| duplicate | 同义重复 | keep_old |
| support | 互相印证 | merge |
| extend | 新信息补充旧 | merge / keep_new |
| replace | 同实体属性被更新 | keep_new |
| contradict | 同实体冲突 | keep_new 或 manual_review |
| unrelated | 主题无关 | keep_old |

主指标：**relation 与 strategy 同时正确**（joint_accuracy）。

### 3.5 forget.jsonl

| 字段 | 规则 |
|------|------|
| `instruction` | 自然语言遗忘请求 |
| `memory_fixtures[]` | 执行前记忆夹具（MemoryRecord） |
| `expected_preview.should_delete_ids` / `should_keep_ids` | 互斥、覆盖夹具 |
| `expected_execute.status_after` | 固定 `tombstoned` |
| `expected_execute.drop_collection_forbidden` | 必须 `true` |
| `requires_second_confirm` | 高风险/全删时 true |

**判定**：preview 按 delete 集合算 P/R；execute 后目标须 tombstone；向量侧无残留；**禁止 DropCollection**；确认令牌由系统派生，标注时不要把「可抄答案的 token」当作唯一金标来源。

### 3.6 security.jsonl

| 字段 | 规则 |
|------|------|
| `input_text` | 待检测文本（假数据） |
| `expected.blocked_or_masked` | bool |
| `expected.entity_type` | password/token/id_card/... 或 null |
| `expected.error_code` | 拦截时为 `SENSITIVE_CONTENT_BLOCKED` |

**判定**：拦截结果与 `entity_type`、错误码均需核对。

---

## 4. 标签与枚举速查（V1.2.1）

- **source**：tool_result / user_behavior / manual_config / cross_scene  
- **preference category**：operation_habit / output_style / tool_choice / safety_policy  
- **conflict relation**：duplicate / support / extend / replace / contradict / unrelated  
- **conflict strategy**：keep_old / keep_new / merge / manual_review  
- **memory status**：active / superseded / tombstoned / expired / pending_review  

场景内容必须属麒麟桌面：终端、安装、办公、网络、安全、开发环境等；禁止纯闲聊。

---

## 5. 质量与复核

| 字段 | 含义 |
|------|------|
| `quality.generation` | 如 `human_curated_template` |
| `quality.human_reviewed` | 是否进入人工复核流程 |

人工复核过程与签字见同目录上级：[`../复核记录.md`](../复核记录.md)。

---

## 6. 变更规则

1. 增删字段或改枚举 → 升 `schema_version`，同步改 loaders/metrics/契约测试。  
2. 只增样本 → 保持 schema，更新复核记录。  
3. 评测脚本不得再内嵌全量 CASES；唯一数据源为本目录 JSONL。
