# Algorithm V1.1 preference_safety donor 快照

## 来源

- 来源分支：`Algorithm---V1.1`
- 来源提交：`8c1e47d`
- 来源归档：`OS_Agent_Memory-Algorithm-V1.1.zip`
- 一致性结论：本目录列出的三个 donor 核心文件与上述提交及 ZIP
  中的对应文件具有相同的 Git-blob SHA-1。

本目录保存算法负责人版本的原始实现，用于追溯、行为对照和 Adapter
集成，不代表这些旧式 `dict` 接口已经符合冻结的 V1.2.2 contracts。

## 不可变文件

- `preference_service.py`
- `safety_service.py`
- `forget_service.py`

**禁止直接修改上述 donor 核心文件。** 对算法行为的修复或契约适配必须
写在本目录之外。若需要升级 donor，应新建带版本的快照目录，重新核验
来源并更新完整性测试，不得在原快照上就地改写。

`README.md`、`__init__.py` 和仓库中的来源完整性测试属于治理元数据，
不属于 donor 核心文件。
