# -*- coding: utf-8 -*-
"""Ground Truth checks for Dataset (4号下周安排建议 · 第三项).

Checks:
1. user_id consistency / isolation
2. multi-gold retrieval integrity
3. conflict relation/strategy direction
4. preference labels (incl. ephemeral)
5. forget delete/keep targets
6. security entity_type / block consistency
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset"
SCENARIOS = ROOT / "scenarios" / "scenarios.json"
REPORT = ROOT / "GT检查报告.md"

PREF_CATEGORIES = {"operation_habit", "output_style", "tool_choice", "safety_policy"}
PREF_SCOPES = {"global", "scene", "tool"}
PREF_EXACT = {
    "preference_key",
    "value",
    "category",
    "scope",
    "scope_value",
    "polarity",
    "status",
}
SOURCES = {"tool_result", "user_behavior", "manual_config", "cross_scene"}
RELATIONS = {"duplicate", "support", "extend", "replace", "contradict", "unrelated"}
STRATEGIES = {"keep_old", "keep_new", "merge", "manual_review"}
# Soft expected strategy by relation (warn if atypical)
RELATION_STRATEGY_HINTS = {
    "duplicate": {"keep_old"},
    "support": {"merge"},
    "extend": {"merge", "keep_new"},
    "replace": {"keep_new"},
    "contradict": {"keep_new", "manual_review"},
    "unrelated": {"keep_old"},
}
ENTITY_TYPES = {
    None,
    "password",
    "token",
    "id_card",
    "bank_card",
    "phone",
    "private_key",
    "address",
}
EPHEMERAL_HINT = re.compile(r"(这次|临时|仅本次|下次不用|只要这一次)")
PUBLIC_USERS = {"usr_corpus_shared"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class Finding:
    def __init__(self, severity: str, area: str, case_id: str, message: str) -> None:
        self.severity = severity  # error | warn | info
        self.area = area
        self.case_id = case_id
        self.message = message

    def as_row(self) -> str:
        return f"| {self.severity} | {self.area} | `{self.case_id}` | {self.message} |"


def check_preference(rows: list[dict]) -> list[Finding]:
    out: list[Finding] = []
    for r in rows:
        cid = r.get("case_id", "?")
        uid = r.get("user_id")
        exp = r.get("expected") or {}
        prefs = exp.get("preferences")
        if prefs is None:
            out.append(Finding("error", "偏好标签", cid, "missing expected.preferences"))
            prefs = []
        ephemeral = bool(exp.get("is_ephemeral_instruction"))
        texts = []
        for ev in r.get("input_events") or []:
            if ev.get("user_id") and ev["user_id"] != uid:
                out.append(
                    Finding(
                        "error",
                        "user_id",
                        cid,
                        f"input_event user_id={ev['user_id']} != case user_id={uid}",
                    )
                )
            if ev.get("source") not in SOURCES:
                out.append(
                    Finding("error", "偏好标签", cid, f"invalid source={ev.get('source')!r}")
                )
            texts.append(((ev.get("payload") or {}).get("text") or ""))
        joined = " ".join(texts)

        if ephemeral and prefs:
            out.append(
                Finding(
                    "error",
                    "偏好标签",
                    cid,
                    "临时指令 is_ephemeral_instruction=true 但 preferences 非空",
                )
            )
        if ephemeral and not exp.get("ephemeral_text"):
            out.append(
                Finding("warn", "偏好标签", cid, "临时指令缺少 ephemeral_text 备注")
            )
        if (not ephemeral) and EPHEMERAL_HINT.search(joined) and prefs:
            out.append(
                Finding(
                    "warn",
                    "偏好标签",
                    cid,
                    "文本含「这次/临时」等，但标为长期偏好——请人工确认",
                )
            )
        if (not ephemeral) and not prefs:
            out.append(
                Finding("warn", "偏好标签", cid, "非临时指令但 preferences 为空")
            )

        for i, pref in enumerate(prefs):
            missing = PREF_EXACT - set(pref)
            if missing:
                out.append(
                    Finding(
                        "error",
                        "偏好标签",
                        cid,
                        f"preferences[{i}] 缺 exact-match 字段 {sorted(missing)}",
                    )
                )
            if pref.get("category") not in PREF_CATEGORIES:
                out.append(
                    Finding(
                        "error",
                        "偏好标签",
                        cid,
                        f"preferences[{i}] invalid category={pref.get('category')!r}",
                    )
                )
            if pref.get("scope") not in PREF_SCOPES:
                out.append(
                    Finding(
                        "error",
                        "偏好标签",
                        cid,
                        f"preferences[{i}] invalid scope={pref.get('scope')!r}",
                    )
                )
    return out


def check_retrieval(rows: list[dict], corpus_ids: dict[str, dict]) -> list[Finding]:
    out: list[Finding] = []
    multi = 0
    empty = 0
    for r in rows:
        cid = r.get("case_id", "?")
        uid = r.get("user_id")
        golds = (r.get("expected") or {}).get("gold_memory_ids")
        if golds is None:
            out.append(Finding("error", "多gold", cid, "missing expected.gold_memory_ids"))
            continue
        if not isinstance(golds, list):
            out.append(Finding("error", "多gold", cid, "gold_memory_ids 必须是 list"))
            continue
        if len(golds) == 0:
            empty += 1
            tags = r.get("tags") or []
            if "no_answer" not in tags:
                out.append(
                    Finding(
                        "warn",
                        "多gold",
                        cid,
                        "空 gold 但未打 no_answer 标签",
                    )
                )
        if len(golds) > 1:
            multi += 1
        if len(golds) != len(set(golds)):
            out.append(Finding("error", "多gold", cid, "gold_memory_ids 有重复"))
        for gid in golds:
            grow = corpus_ids.get(gid)
            if grow is None:
                out.append(
                    Finding("error", "多gold", cid, f"gold {gid} 不在 knowledge_corpus")
                )
                continue
            guid = grow.get("user_id")
            if guid not in PUBLIC_USERS and guid != uid:
                out.append(
                    Finding(
                        "error",
                        "user_id",
                        cid,
                        f"gold {gid} user_id={guid} 既非公共也不等于 query user={uid}",
                    )
                )
            status = grow.get("status")
            if status not in {None, "active"} and "no_answer" not in (r.get("tags") or []):
                # inactive/tombstoned as gold is usually wrong unless intentional hard case
                out.append(
                    Finding(
                        "warn",
                        "多gold",
                        cid,
                        f"gold {gid} status={status}（非 active）",
                    )
                )
    out.append(
        Finding("info", "多gold", "-", f"统计：multi_gold={multi}，empty_gold={empty}，total={len(rows)}")
    )
    return out


def check_conflict(rows: list[dict]) -> list[Finding]:
    out: list[Finding] = []
    rel_cov: Counter[str] = Counter()
    for r in rows:
        cid = r.get("case_id", "?")
        uid = r.get("user_id")
        old, new = r.get("old") or {}, r.get("new") or {}
        exp = r.get("expected") or {}
        rel, strat = exp.get("relation"), exp.get("strategy")
        if rel in RELATIONS:
            rel_cov[rel] += 1
        else:
            out.append(Finding("error", "冲突方向", cid, f"invalid relation={rel!r}"))
        if strat not in STRATEGIES:
            out.append(Finding("error", "冲突方向", cid, f"invalid strategy={strat!r}"))
        if rel in RELATION_STRATEGY_HINTS and strat not in RELATION_STRATEGY_HINTS[rel]:
            out.append(
                Finding(
                    "warn",
                    "冲突方向",
                    cid,
                    f"relation={rel} 配 strategy={strat} 非常见组合（常见 {sorted(RELATION_STRATEGY_HINTS[rel])}）",
                )
            )
        if exp.get("old_memory_id") != old.get("memory_id"):
            out.append(
                Finding(
                    "error",
                    "冲突方向",
                    cid,
                    f"expected.old_memory_id={exp.get('old_memory_id')} != old.memory_id={old.get('memory_id')}",
                )
            )
        if exp.get("new_memory_id") != new.get("memory_id"):
            out.append(
                Finding(
                    "error",
                    "冲突方向",
                    cid,
                    f"expected.new_memory_id={exp.get('new_memory_id')} != new.memory_id={new.get('memory_id')}",
                )
            )
        for key, mem in (("old", old), ("new", new)):
            if mem.get("user_id") and mem["user_id"] != uid:
                out.append(
                    Finding(
                        "error",
                        "user_id",
                        cid,
                        f"{key}.user_id={mem['user_id']} != case user_id={uid}",
                    )
                )
            if not mem.get("content_text"):
                out.append(Finding("error", "冲突方向", cid, f"{key}.content_text 为空"))
        # soft semantic: replace/contradict should share preference_key when both preference-like
        ok = (old.get("content") or {}).get("preference_key")
        nk = (new.get("content") or {}).get("preference_key")
        if rel in {"replace", "contradict", "duplicate", "extend", "support"} and ok and nk:
            if ok != nk and rel != "unrelated":
                out.append(
                    Finding(
                        "warn",
                        "冲突方向",
                        cid,
                        f"relation={rel} 但 preference_key 不同 old={ok} new={nk}",
                    )
                )
        if rel == "unrelated" and ok and nk and ok == nk:
            out.append(
                Finding(
                    "warn",
                    "冲突方向",
                    cid,
                    "标为 unrelated 但 preference_key 相同——请确认",
                )
            )
    missing_rel = RELATIONS - set(rel_cov)
    if missing_rel:
        out.append(
            Finding(
                "warn",
                "冲突方向",
                "-",
                f"六类 relation 未全覆盖：缺 {sorted(missing_rel)}；现有 {dict(rel_cov)}",
            )
        )
    else:
        out.append(
            Finding("info", "冲突方向", "-", f"六类 relation 均有覆盖：{dict(rel_cov)}")
        )
    return out


def check_forget(rows: list[dict]) -> list[Finding]:
    out: list[Finding] = []
    for r in rows:
        cid = r.get("case_id", "?")
        uid = r.get("user_id")
        fixtures = r.get("memory_fixtures") or []
        fix_ids = [f.get("memory_id") for f in fixtures]
        if len(fix_ids) != len(set(fix_ids)):
            out.append(Finding("error", "forget目标", cid, "memory_fixtures 有重复 memory_id"))
        for fx in fixtures:
            if fx.get("user_id") and fx["user_id"] != uid:
                out.append(
                    Finding(
                        "error",
                        "user_id",
                        cid,
                        f"fixture {fx.get('memory_id')} user_id={fx.get('user_id')} != {uid}",
                    )
                )
        prev = r.get("expected_preview") or {}
        exe = r.get("expected_execute") or {}
        delete = list(prev.get("should_delete_ids") or [])
        keep = list(prev.get("should_keep_ids") or [])
        ds, ks = set(delete), set(keep)
        if ds & ks:
            out.append(
                Finding(
                    "error",
                    "forget目标",
                    cid,
                    f"delete∩keep 非空：{sorted(ds & ks)}",
                )
            )
        if set(fix_ids) != ds | ks:
            out.append(
                Finding(
                    "error",
                    "forget目标",
                    cid,
                    f"delete∪keep 未覆盖夹具：fixtures={sorted(fix_ids)} del∪keep={sorted(ds|ks)}",
                )
            )
        if exe.get("status_after") != "tombstoned":
            out.append(
                Finding(
                    "error",
                    "forget目标",
                    cid,
                    f"status_after={exe.get('status_after')!r} 应为 tombstoned",
                )
            )
        if exe.get("drop_collection_forbidden") is not True:
            out.append(
                Finding(
                    "error",
                    "forget目标",
                    cid,
                    "drop_collection_forbidden 必须为 true",
                )
            )
        if set(exe.get("deleted_ids") or []) != ds:
            out.append(
                Finding(
                    "error",
                    "forget目标",
                    cid,
                    "expected_execute.deleted_ids 与 preview.should_delete_ids 不一致",
                )
            )
        if r.get("requires_second_confirm") and not prev.get("confirmation_required"):
            out.append(
                Finding(
                    "warn",
                    "forget目标",
                    cid,
                    "requires_second_confirm=true 但 preview.confirmation_required 未置 true",
                )
            )
        # empty delete is allowed for boundary cases but should be tagged
        if not ds and "boundary" not in " ".join(r.get("tags") or []):
            out.append(
                Finding(
                    "warn",
                    "forget目标",
                    cid,
                    "should_delete_ids 为空——确认是否边界用例",
                )
            )
    return out


def check_security(rows: list[dict]) -> list[Finding]:
    out: list[Finding] = []
    for r in rows:
        cid = r.get("case_id", "?")
        exp = r.get("expected") or {}
        blocked = exp.get("blocked_or_masked")
        et = exp.get("entity_type")
        code = exp.get("error_code")
        text = r.get("input_text") or ""
        if et not in ENTITY_TYPES:
            out.append(
                Finding("error", "security实体", cid, f"未知 entity_type={et!r}")
            )
        if blocked is True:
            if et is None:
                out.append(
                    Finding(
                        "error",
                        "security实体",
                        cid,
                        "blocked=true 但 entity_type 为 null",
                    )
                )
            if code != "SENSITIVE_CONTENT_BLOCKED":
                out.append(
                    Finding(
                        "error",
                        "security实体",
                        cid,
                        f"blocked=true 但 error_code={code!r}",
                    )
                )
            # soft: entity keyword presence
            hints = {
                "password": r"(密\s*码|password|pwd\s*=)",
                "token": r"(token|sk-|令牌)",
                "id_card": r"(身份证|\d{17}[\dXx])",
                "bank_card": r"(银行卡|\d{16,19})",
                "phone": r"(手机号|1[3-9]\d{9})",
                "private_key": r"(私钥|BEGIN|SSH)",
                "address": r"(地址|路|区)",
            }
            if et in hints and not re.search(hints[et], text, re.I):
                out.append(
                    Finding(
                        "warn",
                        "security实体",
                        cid,
                        f"entity_type={et} 与文本弱匹配——请人工确认",
                    )
                )
        if blocked is False:
            if et is not None:
                out.append(
                    Finding(
                        "error",
                        "security实体",
                        cid,
                        f"blocked=false 但 entity_type={et!r}（应为 null）",
                    )
                )
            if code not in (None, ""):
                out.append(
                    Finding(
                        "warn",
                        "security实体",
                        cid,
                        f"blocked=false 但带有 error_code={code!r}",
                    )
                )
        if not text.strip():
            out.append(Finding("error", "security实体", cid, "input_text 为空"))
    return out


def check_scenarios(corpus_ids: dict[str, dict], indexes: dict[str, dict]) -> list[Finding]:
    out: list[Finding] = []
    if not SCENARIOS.exists():
        out.append(Finding("warn", "user_id", "-", "scenarios.json 不存在"))
        return out
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    for scn in scenarios:
        sid = scn["scenario_id"]
        uid = scn["user_id"]
        private = scn.get("ref_private_cases") or []
        for cid in private:
            row = indexes.get(cid)
            if row is None:
                out.append(Finding("error", "user_id", sid, f"私有引用缺失 {cid}"))
                continue
            if row.get("user_id") != uid and cid.startswith(("PREF-", "CONF-", "FORG-", "RET-", "SEC-")):
                # RET with public gold but query user must match
                out.append(
                    Finding(
                        "error",
                        "user_id",
                        sid,
                        f"{cid} user_id={row.get('user_id')} != scenario {uid}",
                    )
                )
        for mid in scn.get("ref_public_memory_ids") or []:
            grow = corpus_ids.get(mid)
            if grow is None:
                out.append(Finding("error", "user_id", sid, f"公共记忆缺失 {mid}"))
            elif grow.get("user_id") not in PUBLIC_USERS:
                out.append(
                    Finding(
                        "error",
                        "user_id",
                        sid,
                        f"{mid} 标为公共但 user_id={grow.get('user_id')}",
                    )
                )
    return out


def build_index() -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for fname in (
        "preference.jsonl",
        "retrieval_queries.jsonl",
        "conflict.jsonl",
        "forget.jsonl",
        "security.jsonl",
    ):
        for row in load_jsonl(DATASET / fname):
            if row.get("case_id"):
                idx[row["case_id"]] = row
    return idx


def run() -> tuple[list[Finding], dict[str, Any]]:
    corpus = load_jsonl(DATASET / "knowledge_corpus.jsonl")
    corpus_ids = {r["memory_id"]: r for r in corpus}
    prefs = load_jsonl(DATASET / "preference.jsonl")
    rets = load_jsonl(DATASET / "retrieval_queries.jsonl")
    confs = load_jsonl(DATASET / "conflict.jsonl")
    forg = load_jsonl(DATASET / "forget.jsonl")
    secs = load_jsonl(DATASET / "security.jsonl")
    idx = build_index()

    findings: list[Finding] = []
    findings.extend(check_preference(prefs))
    findings.extend(check_retrieval(rets, corpus_ids))
    findings.extend(check_conflict(confs))
    findings.extend(check_forget(forg))
    findings.extend(check_security(secs))
    findings.extend(check_scenarios(corpus_ids, idx))

    summary = {
        "date": str(date.today()),
        "counts": {
            "preference": len(prefs),
            "corpus": len(corpus),
            "retrieval": len(rets),
            "conflict": len(confs),
            "forget": len(forg),
            "security": len(secs),
        },
        "errors": sum(1 for f in findings if f.severity == "error"),
        "warns": sum(1 for f in findings if f.severity == "warn"),
        "infos": sum(1 for f in findings if f.severity == "info"),
    }
    return findings, summary


def write_report(findings: list[Finding], summary: dict[str, Any]) -> None:
    by_area: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_area[f.area].append(f)

    lines = [
        "# Ground Truth 检查报告",
        "",
        f"**日期**：{summary['date']}  ",
        "**依据**：`4号下周安排建议.docx` 第三项 + `dataset/README.md`  ",
        f"**规模**：{summary['counts']}  ",
        f"**结果**：error={summary['errors']}，warn={summary['warns']}，info={summary['infos']}",
        "",
        "## 结论",
        "",
    ]
    if summary["errors"] == 0:
        lines.append(
            "**结构性 GT 检查通过（无 error）。** warn 项需人工扫一眼；不影响三分法冻结使用。"
        )
    else:
        lines.append(
            f"**存在 {summary['errors']} 条 error，须先修复再进入失败归因 / E2E。**"
        )

    lines += [
        "",
        "## 六项覆盖",
        "",
        "| 检查项 | error | warn | info |",
        "|--------|------:|-----:|-----:|",
    ]
    areas = ["user_id", "多gold", "冲突方向", "偏好标签", "forget目标", "security实体"]
    for area in areas:
        fs = by_area.get(area, [])
        lines.append(
            f"| {area} | {sum(1 for f in fs if f.severity=='error')} | "
            f"{sum(1 for f in fs if f.severity=='warn')} | "
            f"{sum(1 for f in fs if f.severity=='info')} |"
        )

    lines += [
        "",
        "## 明细",
        "",
        "| 级别 | 项 | case_id | 说明 |",
        "|------|----|---------|------|",
    ]
    # errors first, then warns, skip pure info in table except keep infos in section
    for sev in ("error", "warn"):
        for f in findings:
            if f.severity == sev:
                lines.append(f.as_row())
    infos = [f for f in findings if f.severity == "info"]
    if infos:
        lines += ["", "## 统计信息", ""]
        for f in infos:
            lines.append(f"- **{f.area}**：{f.message}")

    lines += [
        "",
        "## 下一步",
        "",
        "1. 修复全部 error（若有）",
        "2. 人工过一遍 warn",
        "3. 建立失败案例归因表（安排第四项）",
        "4. 推进 5 个精品 E2E 跑通（安排第五项）",
        "",
        "复跑：`python -m evaluation.check_ground_truth`",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    findings, summary = run()
    write_report(findings, summary)
    print(f"errors={summary['errors']} warns={summary['warns']} infos={summary['infos']}")
    print(f"report -> {REPORT}")
    for f in findings:
        if f.severity == "error":
            print(f"[error][{f.area}] {f.case_id}: {f.message}")
    for f in findings:
        if f.severity == "warn":
            print(f"[warn][{f.area}] {f.case_id}: {f.message}")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
