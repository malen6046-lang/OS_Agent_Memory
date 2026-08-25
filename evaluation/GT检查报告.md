# Ground Truth 检查报告

**日期**：2026-08-25  
**依据**：`4号下周安排建议.docx` 第三项 + `dataset/README.md`  
**规模**：{'preference': 67, 'corpus': 68, 'retrieval': 90, 'conflict': 29, 'forget': 30, 'security': 46}  
**结果**：error=0，warn=0，info=2

## 结论

**结构性 GT 检查通过（无 error）。** warn 项需人工扫一眼；不影响三分法冻结使用。

## 六项覆盖

| 检查项 | error | warn | info |
|--------|------:|-----:|-----:|
| user_id | 0 | 0 | 0 |
| 多gold | 0 | 0 | 1 |
| 冲突方向 | 0 | 0 | 1 |
| 偏好标签 | 0 | 0 | 0 |
| forget目标 | 0 | 0 | 0 |
| security实体 | 0 | 0 | 0 |

## 明细

| 级别 | 项 | case_id | 说明 |
|------|----|---------|------|

## 统计信息

- **多gold**：统计：multi_gold=18，empty_gold=5，total=90
- **冲突方向**：六类 relation 均有覆盖：{'replace': 7, 'contradict': 7, 'duplicate': 5, 'support': 3, 'extend': 4, 'unrelated': 3}

## 下一步

1. 修复全部 error（若有）
2. 人工过一遍 warn
3. 建立失败案例归因表（安排第四项）
4. 推进 5 个精品 E2E 跑通（安排第五项）

复跑：`python -m evaluation.check_ground_truth`
