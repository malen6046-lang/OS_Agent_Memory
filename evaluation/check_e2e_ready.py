# -*- coding: utf-8 -*-
"""Data-layer E2E readiness check for SCN-01..05 (安排第五项 · 4号侧).

Validates: single user_id refs exist, preference/conflict/forget/retrieval golds
are consistent. Does NOT execute real Preference/Knowledge/Forget services —
that remains 1/2号联调回填.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset"
SCENARIOS = ROOT / "scenarios" / "scenarios.json"
REPORT = ROOT / "E2E跑通清单.md"

# 精品五场景（安排：先 5 个，不追求 20）
PREMIUM = ("SCN-01", "SCN-02", "SCN-03", "SCN-04", "SCN-05")

ROLE_LABEL = {
    "flagship": "旗舰全链路",
    "full_e2e": "完整 E2E",
    "retrieval_only": "检索专项",
    "forget_focus": "遗忘专项",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def index_all() -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for name in (
        "preference.jsonl",
        "retrieval_queries.jsonl",
        "conflict.jsonl",
        "forget.jsonl",
        "security.jsonl",
    ):
        for row in load_jsonl(DATASET / name):
            if row.get("case_id"):
                idx[row["case_id"]] = row
    for row in load_jsonl(DATASET / "knowledge_corpus.jsonl"):
        if row.get("memory_id"):
            idx[row["memory_id"]] = row
    return idx


def check_scenario(scn: dict[str, Any], idx: dict[str, dict[str, Any]]) -> list[str]:
    errs: list[str] = []
    sid = scn["scenario_id"]
    uid = scn["user_id"]
    private = scn.get("ref_private_cases") or []
    public = scn.get("ref_public_memory_ids") or []

    if not private and sid != "SCN-04":
        errs.append("无私有用例引用（SCN-04 除外）")

    for cid in private:
        row = idx.get(cid)
        if row is None:
            errs.append(f"缺失用例 {cid}")
            continue
        if row.get("user_id") != uid:
            errs.append(f"{cid} user_id={row.get('user_id')} != {uid}")

    for mid in public:
        row = idx.get(mid)
        if row is None:
            errs.append(f"缺失公共记忆 {mid}")
        elif row.get("user_id") != "usr_corpus_shared":
            errs.append(f"{mid} 非公共 user_id={row.get('user_id')}")

    # flow coverage hints
    kinds = {cid.split("-", 1)[0] for cid in private if "-" in cid}
    if sid in {"SCN-01", "SCN-02", "SCN-03"} and "PREF" not in kinds:
        errs.append("缺少 PREF 引用")
    if sid == "SCN-05" and "FORG" not in kinds:
        errs.append("缺少 FORG 引用")
    if sid == "SCN-04" and not public and "RET" not in kinds:
        # SCN-04 may use RET in ref_cases
        refs = scn.get("ref_cases") or []
        if not any(str(x).startswith("RET-") for x in refs):
            errs.append("知识问答缺少 RET/公共语料引用")

    turns = scn.get("turns") or []
    if not turns:
        errs.append("scenarios.json 缺少 turns[] 结构化回合")
    else:
        tids = [t.get("turn_id") for t in turns]
        if len(tids) != len(set(tids)):
            errs.append("turn_id 重复")
        demo = scn.get("demo_path") or []
        for tid in demo:
            if tid not in tids:
                errs.append(f"demo_path 引用未知回合 {tid}")

    return errs


def write_report(results: list[dict[str, Any]]) -> None:
    lines = [
        "# 5 个精品 E2E 跑通清单",
        "",
        "**依据**：`4号下周安排建议.docx` 第五项  ",
        "**目标**：先做到 5 个精品场景完全跑通（不用 20 个）  ",
        "**标准链路**：",
        "",
        "```text",
        "单一 user_id → 输入 → 记忆形成 → 检索 → 更新/冲突 → 遗忘 → 结果验证",
        "```",
        "",
        "## 数据层就绪（4号）",
        "",
        "| 场景 | user_id | 定位 | 回合数 | 数据层 | 实机联调 | 说明 |",
        "|------|---------|------|--------|--------|----------|------|",
    ]
    for r in results:
        data = "✅" if r["data_ok"] else "❌"
        e2e = r.get("e2e_status", "待联调")
        note = "; ".join(r["errors"]) if r["errors"] else "引用齐全 / 用户隔离 OK"
        role = r.get("role_label", "")
        n_turns = r.get("turn_count", 0)
        lines.append(
            f"| {r['id']} {r['name']} | `{r['user_id']}` | {role} | {n_turns} | {data} | {e2e} | {note} |"
        )

    lines += [
        "",
        "## 每场景必跑检查（1/2号联调时勾选）",
        "",
        "对每个 SCN-01…05：",
        "",
        "- [ ] 全程只有剧本中的单一 `user_id`",
        "- [ ] 初次输入能写入/抽取记忆（偏好或知识）",
        "- [ ] 第二次调用能检索到预期记忆",
        "- [ ] 若有冲突：relation/strategy 与 GT 一致",
        "- [ ] 若有遗忘：delete/keep 与 GT 一致，且未 DropCollection",
        "- [ ] 结果与场景文档「预期结果」一致；填写「联调回填」",
        "",
        "## 场景文件",
        "",
        "| ID | 文档 |",
        "|----|------|",
        "| SCN-01 | [`scenarios/01_开发助手.md`](./scenarios/01_开发助手.md) |",
        "| SCN-02 | [`scenarios/02_办公助手.md`](./scenarios/02_办公助手.md) |",
        "| SCN-03 | [`scenarios/03_系统维护助手.md`](./scenarios/03_系统维护助手.md) |",
        "| SCN-04 | [`scenarios/04_知识问答.md`](./scenarios/04_知识问答.md) |",
        "| SCN-05 | [`scenarios/05_遗忘操作.md`](./scenarios/05_遗忘操作.md) |",
        "",
        "## 联调入口",
        "",
        "见 [`联调注入说明.md`](./联调注入说明.md)。注入服务后：",
        "",
        "```bash",
        "python -m evaluation.run_all --split dev",
        "python -m evaluation.collect_failures --split dev",
        "python -m evaluation.check_scenario_user_consistency",
        "python -m evaluation.check_e2e_ready",
        "python -m evaluation.run_scenario --id SCN-01",
        "python -m evaluation.run_scenario --validate",
        "```",
        "",
        "联调完成后更新各场景 md 末尾「联调回填」，并改 `scenarios.json` 的 `actual_result_status`。",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    scenarios = {
        s["scenario_id"]: s for s in json.loads(SCENARIOS.read_text(encoding="utf-8"))
    }
    idx = index_all()
    results = []
    any_err = False
    for sid in PREMIUM:
        scn = scenarios.get(sid)
        if scn is None:
            results.append(
                {
                    "id": sid,
                    "name": "?",
                    "user_id": "?",
                    "data_ok": False,
                    "errors": ["scenarios.json 中缺失"],
                    "e2e_status": "—",
                }
            )
            any_err = True
            continue
        errs = check_scenario(scn, idx)
        status = scn.get("actual_result_status", "pending")
        results.append(
            {
                "id": sid,
                "name": scn.get("name", ""),
                "user_id": scn.get("user_id", ""),
                "role_label": ROLE_LABEL.get(scn.get("role", ""), scn.get("role", "")),
                "turn_count": len(scn.get("turns") or []),
                "data_ok": not errs,
                "errors": errs,
                "e2e_status": status,
            }
        )
        if errs:
            any_err = True
    write_report(results)
    ok_n = sum(1 for r in results if r["data_ok"])
    print(f"premium data-ready {ok_n}/{len(PREMIUM)}")
    print(f"report -> {REPORT}")
    for r in results:
        mark = "OK" if r["data_ok"] else "FAIL"
        print(f"  [{mark}] {r['id']} {r['name']} e2e={r['e2e_status']}")
        for e in r["errors"]:
            print(f"       - {e}")
    return 1 if any_err else 0


if __name__ == "__main__":
    sys.exit(main())
