# -*- coding: utf-8 -*-
"""Append V0.3 quality-focused dev samples (dev split only; validation/final_test frozen)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "evaluation" / "dataset"

PROV_PREF = {
    "inspired_by": "LaMP user-history-to-preference format",
    "license_note": "仅借鉴任务结构；样本为原创麒麟OS场景",
    "adaptation": "字段对齐 V1.2.1 schema + V1.2.2 freeze Envelope/PreferenceRecord",
}
PROV_RET = {
    "inspired_by": "BEIR corpus-query-qrels format",
    "license_note": "仅借鉴评测思想；知识为原创",
    "adaptation": "gold 以 memory_id 为准，对齐 V1.2.1 schema + V1.2.2 freeze §12.1",
}
PROV_CONF = {
    "inspired_by": "SNLI/MNLI relation labels mapped to OS conflict",
    "license_note": "仅借鉴任务结构；样本原创",
    "adaptation": "relation/strategy 对齐 V1.2.1 schema + V1.2.2 freeze ConflictDecision",
}
PROV_FORG = {
    "inspired_by": "TOFU forget-request and residual evaluation",
    "license_note": "样本原创",
    "adaptation": "对齐 V1.2.1 schema + V1.2.2 freeze forget preview/execute 与 tombstone 语义",
}
PROV_SEC = {
    "inspired_by": "TOFU/unlearning target removal + safety filter practice",
    "license_note": "假数据；样本原创",
}


def pref(
    cid: str,
    uid: str,
    scene: str,
    text: str,
    source: str,
    prefs: list[dict],
    *,
    ephemeral: bool = False,
    ephemeral_text: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    evt = f"evt_{cid.replace('-', '_').lower()}"
    row = {
        "schema_version": "0.1.0",
        "case_id": cid,
        "task_type": "preference_extract",
        "split": "dev",
        "scene": scene,
        "user_id": uid,
        "input_events": [
            {
                "contract_version": "1.0",
                "request_id": f"req_{cid.replace('-', '_').lower()}",
                "idempotency_key": f"idem_{cid.replace('-', '_').lower()}",
                "user_id": uid,
                "session_id": None,
                "scene": scene,
                "source": source,
                "source_event_id": evt,
                "occurred_at": "2026-08-20T10:00:00+08:00",
                "payload": {"text": text},
            }
        ],
        "expected": {
            "preferences": prefs,
            "is_ephemeral_instruction": ephemeral,
        },
        "evaluation": {
            "primary_metric": "preference_exact_match",
            "also_report": ["macro_f1", "ephemeral_false_positive_rate"],
        },
        "tags": tags or ["银河麒麟V11", "中文", "v0.3_quality"],
        "provenance": PROV_PREF,
        "quality": {"generation": "v0.3_quality_expand", "human_reviewed": True},
    }
    if ephemeral and ephemeral_text:
        row["expected"]["ephemeral_text"] = ephemeral_text
    return row


def ret(
    cid: str,
    uid: str,
    query: str,
    gold: list[str],
    *,
    scene: str = "galaxy_kylin_v11",
    tags: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "0.1.0",
        "case_id": cid,
        "task_type": "knowledge_retrieval",
        "split": "dev",
        "user_id": uid,
        "scene": scene,
        "query": query,
        "top_k": [1, 3, 5, 10],
        "expected": {"gold_memory_ids": gold},
        "evaluation": {
            "primary_metric": "recall_at_k",
            "match": "memory_id",
            "also_report": ["mrr", "latency_p50_p95"],
        },
        "tags": tags or ["银河麒麟V11", "中文", "retrieval", "v0.3_quality"],
        "provenance": PROV_RET,
        "quality": {"generation": "v0.3_quality_expand", "human_reviewed": True},
    }


def conf(
    cid: str,
    uid: str,
    scene: str,
    old_kv: dict,
    new_kv: dict,
    relation: str,
    strategy: str,
    *,
    tags: list[str] | None = None,
    new_valid_from: str = "2026-07-20T15:00:00+08:00",
    new_confidence: float = 0.9,
    new_revision: int = 1,
) -> dict:
    old_id = f"mem_old_{cid.replace('-', '_').lower()}"
    new_id = f"mem_new_{cid.replace('-', '_').lower()}"

    def mem(mid: str, kv: dict, *, side: str) -> dict:
        key = list(kv.keys())[0]
        val = kv[key]
        side_label = "旧记忆" if side == "old" else "新记忆"
        return {
            "memory_id": mid,
            "user_id": uid,
            "memory_kind": "preference",
            "subtype": "operation_habit",
            "content_text": f"{side_label}：{key}={val}",
            "content": {"preference_key": key, "value": val},
            "status": "active",
            "confidence": 0.85 if side == "old" else new_confidence,
            "importance": 0.6,
            "revision": 1 if side == "old" else new_revision,
            "valid_from": "2026-07-01T09:00:00+08:00"
            if side == "old"
            else new_valid_from,
            "valid_to": None,
            "expires_at": None,
            "scene_tags": ["galaxy_kylin_v11"],
            "source_refs": [f"evt_{mid}"],
            "supersedes": [],
            "attributes": {},
        }

    return {
        "schema_version": "0.1.0",
        "case_id": cid,
        "task_type": "knowledge_conflict",
        "split": "dev",
        "user_id": uid,
        "scene": scene,
        "old": mem(old_id, old_kv, side="old"),
        "new": mem(new_id, new_kv, side="new"),
        "expected": {
            "relation": relation,
            "strategy": strategy,
            "confidence": 0.89,
            "reason_codes": ["same_entity", "same_attribute", "newer_effective_at"],
            "old_memory_id": old_id,
            "new_memory_id": new_id,
        },
        "evaluation": {
            "primary_metric": "conflict_accuracy",
            "also_report": ["confusion_matrix", "manual_review_rate", "auto_apply_rate"],
        },
        "tags": tags or ["银河麒麟V11", "冲突", relation, "v0.3_quality"],
        "provenance": PROV_CONF,
        "quality": {"generation": "v0.3_quality_expand", "human_reviewed": True},
    }


def forg(
    cid: str,
    uid: str,
    instruction: str,
    fixtures: list[str],
    delete_ids: list[str],
    keep_ids: list[str],
    *,
    scene: str = "office_automation",
) -> dict:
    token = f"tok_{cid.replace('-', '_').lower()}"

    def fix(mid: str) -> dict:
        return {
            "memory_id": mid,
            "user_id": uid,
            "memory_kind": "semantic",
            "subtype": "fact",
            "content_text": f"夹具记忆 {mid}",
            "content": {"label": mid},
            "status": "active",
            "confidence": 0.8,
            "importance": 0.5,
            "revision": 1,
            "valid_from": "2026-07-01T09:00:00+08:00",
            "valid_to": None,
            "expires_at": None,
            "scene_tags": [scene],
            "source_refs": [f"evt_fix_{mid}"],
            "supersedes": [],
            "attributes": {},
        }

    return {
        "schema_version": "0.1.0",
        "case_id": cid,
        "task_type": "precise_forget",
        "split": "dev",
        "user_id": uid,
        "scene": scene,
        "instruction": instruction,
        "requires_second_confirm": False,
        "setup_memory_ids": fixtures,
        "memory_fixtures": [fix(m) for m in fixtures],
        "expected_preview": {
            "should_delete_ids": delete_ids,
            "should_keep_ids": keep_ids,
            "risk_level": "medium",
            "confirmation_token": token,
            "confirmation_required": False,
        },
        "expected_execute": {
            "confirmation_token": token,
            "deleted_ids": delete_ids,
            "status_after": "tombstoned",
            "residual_in_sqlite": False,
            "residual_in_vector": False,
            "false_delete_ids": [],
            "drop_collection_forbidden": True,
        },
        "evaluation": {
            "primary_metric": "forget_precision_recall",
            "also_report": ["false_delete_rate", "residual_check"],
        },
        "tags": ["银河麒麟V11", "forget", "preview_execute", "v0.3_quality", "boundary"],
        "provenance": PROV_FORG,
        "quality": {"generation": "v0.3_quality_expand", "human_reviewed": True},
    }


def sec(cid: str, uid: str, text: str, blocked: bool, entity: str | None) -> dict:
    return {
        "schema_version": "0.1.0",
        "case_id": cid,
        "task_type": "sensitive_filter",
        "split": "dev",
        "user_id": uid,
        "input_text": text,
        "expected": {
            "blocked_or_masked": blocked,
            "entity_type": entity,
            "error_code": "SENSITIVE_CONTENT_BLOCKED" if blocked else None,
        },
        "tags": ["security", "kylin", "v0.3_quality"],
        "provenance": PROV_SEC,
        "quality": {"generation": "v0.3_quality_expand", "human_reviewed": True},
    }


def corpus(mid: str, title: str, body: str, keywords: list[str], subtype: str = "workflow") -> dict:
    return {
        "memory_id": mid,
        "user_id": "usr_corpus_shared",
        "memory_kind": "semantic",
        "subtype": subtype,
        "content_text": f"{title}。{body}",
        "content": {
            "title": title,
            "knowledge_type": subtype,
            "body": body,
            "steps": [body],
            "keywords": keywords,
            "source_uri": None,
            "source_reliability": 0.85,
            "effective_at": "2026-07-01T09:00:00+08:00",
        },
        "status": "active",
        "confidence": 0.9,
        "importance": 0.7,
        "revision": 1,
        "valid_from": "2026-07-01T09:00:00+08:00",
        "valid_to": None,
        "expires_at": None,
        "scene_tags": ["galaxy_kylin_v11"],
        "source_refs": [f"evt_{mid}"],
        "supersedes": [],
        "attributes": {"domain": "kylin_desktop"},
    }


NEW_PREFERENCE = [
    pref("PREF-0058", "usr_kylin_001", "office_automation", "连续一周会议纪要都要求先列三条结论", "user_behavior",
         [{"preference_key": "output.structure", "value": "conclusion_first", "category": "output_style", "scope": "global", "scope_value": "global", "polarity": "positive", "confidence": 0.88, "evidence_count": 1, "evidence": [{"source_event_id": "evt_pref_0058", "weight": 0.8}], "revision": 1, "status": "active"}],
         tags=["隐式偏好", "output_style", "user_behavior"]),
    pref("PREF-0059", "usr_kylin_002", "software_dev", "三次提交都要求附带单元测试文件列表", "user_behavior",
         [{"preference_key": "output.structure", "value": "include_test_list", "category": "output_style", "scope": "global", "scope_value": "global", "polarity": "positive", "confidence": 0.88, "evidence_count": 1, "evidence": [{"source_event_id": "evt_pref_0059", "weight": 0.8}], "revision": 1, "status": "active"}],
         tags=["隐式偏好", "software_dev"]),
    pref("PREF-0060", "usr_kylin_005", "office_automation", "用户多次要求表格用制表符对齐", "user_behavior",
         [{"preference_key": "output.format", "value": "tab_aligned_table", "category": "output_style", "scope": "global", "scope_value": "global", "polarity": "positive", "confidence": 0.88, "evidence_count": 1, "evidence": [{"source_event_id": "evt_pref_0060", "weight": 0.8}], "revision": 1, "status": "active"}],
         tags=["隐式偏好", "office_automation"]),
    pref("PREF-0061", "usr_kylin_003", "system_maintenance", "习惯把日志级别默认设为 INFO", "user_behavior",
         [{"preference_key": "logging.level", "value": "info", "category": "operation_habit", "scope": "global", "scope_value": "global", "polarity": "positive", "confidence": 0.88, "evidence_count": 1, "evidence": [{"source_event_id": "evt_pref_0061", "weight": 0.8}], "revision": 1, "status": "active"}],
         tags=["operation_habit"]),
    pref("PREF-0062", "usr_kylin_004", "software_dev", "这次回答请用英文，以后还是中文", "user_behavior", [],
         ephemeral=True, ephemeral_text="output.language=en", tags=["临时指令", "ephemeral"]),
    pref("PREF-0063", "usr_kylin_005", "office_automation", "仅本次导出 PDF，平时仍用 Markdown", "user_behavior", [],
         ephemeral=True, ephemeral_text="output.format=pdf_once", tags=["临时指令", "ephemeral"]),
    pref("PREF-0064", "usr_kylin_002", "software_dev", "临时用 vim 改这一个文件，别改默认 IDE", "user_behavior", [],
         ephemeral=True, ephemeral_text="tool.editor=vim_once", tags=["临时指令", "ephemeral"]),
    pref("PREF-0065", "usr_kylin_001", "galaxy_kylin_v11", "默认输入法使用搜狗拼音", "manual_config",
         [{"preference_key": "input.method", "value": "sogou_pinyin", "category": "tool_choice", "scope": "global", "scope_value": "global", "polarity": "positive", "confidence": 0.88, "evidence_count": 1, "evidence": [{"source_event_id": "evt_pref_0065", "weight": 0.8}], "revision": 1, "status": "active"}],
         tags=["tool_choice"]),
    pref("PREF-0066", "usr_kylin_003", "system_maintenance", "清理磁盘时优先清理缓存目录", "user_behavior",
         [{"preference_key": "cleanup.priority", "value": "temp_dirs_first", "category": "operation_habit", "scope": "global", "scope_value": "global", "polarity": "positive", "confidence": 0.88, "evidence_count": 1, "evidence": [{"source_event_id": "evt_pref_0066", "weight": 0.8}], "revision": 1, "status": "active"}],
         tags=["隐式偏好", "system_maintenance"]),
    pref("PREF-0067", "usr_kylin_004", "software_dev", "代码注释默认使用中文", "manual_config",
         [{"preference_key": "output.comment_language", "value": "zh", "category": "output_style", "scope": "global", "scope_value": "global", "polarity": "positive", "confidence": 0.88, "evidence_count": 1, "evidence": [{"source_event_id": "evt_pref_0067", "weight": 0.8}], "revision": 1, "status": "active"}]),
]

NEW_RETRIEVAL = [
    ret("RET-0079", "usr_corpus_shared", "命令行窗口怎么开？", ["mem_kb_0001"], tags=["hard", "p3", "同义表达", "v0.3_quality"]),
    ret("RET-0080", "usr_corpus_shared", "Ctrl+Alt+T 能打开什么？", ["mem_kb_0001"], tags=["hard", "p3", "同义表达"]),
    ret("RET-0081", "usr_corpus_shared", "麒麟桌面启动终端的快捷键是什么？", ["mem_kb_0001"], tags=["hard", "p3", "同义表达"]),
    ret("RET-0082", "usr_corpus_shared", "应用商店怎么装软件？", ["mem_kb_0002"], tags=["hard", "p3", "同义表达"]),
    ret("RET-0083", "usr_corpus_shared", "从商店安装 WPS 的流程？", ["mem_kb_0002"], tags=["hard", "p3", "同义表达"]),
    ret("RET-0084", "usr_corpus_shared", "如何打开终端并查看系统版本？", ["mem_kb_0001", "mem_kb_0011"], tags=["hard", "p3", "multi_gold"]),
    ret("RET-0085", "usr_corpus_shared", "怎样查看麒麟版本号？", ["mem_kb_0011"], tags=["retrieval"]),
    ret("RET-0086", "usr_corpus_shared", "银河麒麟如何安装不存在版本的驱动 XYZ-999？", [], tags=["hard", "p3", "no_answer"]),
    ret("RET-0087", "usr_corpus_shared", "怎么配置量子加密网卡 QEN-2026？", [], tags=["hard", "p3", "no_answer"]),
    ret("RET-0088", "usr_kylin_004", "我习惯用什么 IDE？", [], scene="software_dev", tags=["cross_user", "private_preference", "no_answer"]),
    ret("RET-0089", "usr_kylin_004", "怎样打开麒麟系统的终端？", ["mem_kb_0001"], scene="software_dev", tags=["public_knowledge_gold", "user_isolated"]),
    ret("RET-0090", "usr_corpus_shared", "输入法怎么切换？", ["mem_kb_0059"], tags=["hard", "p3", "同义表达"]),
]

NEW_CONFLICT = [
    conf(
        "CONF-0024",
        "usr_kylin_001",
        "office_automation",
        {"tool.office": "libreoffice"},
        {"tool.office": "wps"},
        "replace",
        "keep_new",
        tags=["replace"],
    ),
    conf(
        "CONF-0025",
        "usr_kylin_002",
        "software_dev",
        {"tool.editor": "vscode"},
        {"tool.editor": "kylin_ide"},
        "replace",
        "keep_new",
        tags=["replace"],
    ),
    conf(
        "CONF-0026",
        "usr_kylin_003",
        "system_maintenance",
        {"workflow.backup": "full_local"},
        {"workflow.backup": "incremental_local"},
        "replace",
        "keep_new",
        tags=["replace"],
    ),
    conf(
        "CONF-0027",
        "usr_kylin_004",
        "software_dev",
        {"output.structure": "complete_tree"},
        {"output.structure": "complete_tree"},
        "duplicate",
        "keep_old",
        tags=["duplicate"],
    ),
    conf(
        "CONF-0028",
        "usr_kylin_005",
        "office_automation",
        {"output.format": "markdown"},
        {"tool.browser": "firefox"},
        "unrelated",
        "keep_old",
        tags=["unrelated"],
    ),
    conf(
        "CONF-0029",
        "usr_kylin_001",
        "galaxy_kylin_v11",
        {"ui.theme": "dark"},
        {"ui.theme": "light"},
        "contradict",
        "keep_new",
        tags=["contradict"],
        new_valid_from="2026-08-01T10:00:00+08:00",
        new_confidence=0.92,
        new_revision=2,
    ),
]

NEW_FORGET = [
    forg("FORG-0025", "usr_kylin_005", "忘掉周报模板偏好，WPS 设置保留", ["mem_weekly_tpl", "mem_wps_pref", "mem_font"], ["mem_weekly_tpl"], ["mem_wps_pref", "mem_font"]),
    forg("FORG-0026", "usr_kylin_004", "删除代码注释语言偏好，编辑器偏好留下", ["mem_comment_lang", "mem_editor", "mem_tree"], ["mem_comment_lang"], ["mem_editor", "mem_tree"], scene="software_dev"),
    forg("FORG-0027", "usr_kylin_003", "忘记临时清理策略，备份与防火墙记忆保留", ["mem_cleanup_tmp", "mem_backup_pol", "mem_fw_on"], ["mem_cleanup_tmp"], ["mem_backup_pol", "mem_fw_on"], scene="system_maintenance"),
    forg("FORG-0028", "usr_kylin_002", "忘掉深色主题，文件排序偏好别动", ["mem_theme_dark", "mem_sort_mtime", "mem_ide"], ["mem_theme_dark"], ["mem_sort_mtime", "mem_ide"]),
    forg("FORG-0029", "usr_kylin_001", "删除输入法偏好，办公套件偏好保留", ["mem_input_method", "mem_office_wps"], ["mem_input_method"], ["mem_office_wps"]),
    forg("FORG-0030", "usr_kylin_005", "忘记会议专项细节，纪要结构习惯保留", ["mem_proj_detail", "mem_minutes_style"], ["mem_proj_detail"], ["mem_minutes_style"]),
]

NEW_SECURITY = [
    sec("SEC-0041", "usr_kylin_005", "会议纪要先写结论再附表格", False, None),
    sec("SEC-0042", "usr_kylin_003", "开启防火墙并设置锁屏300秒", False, None),
    sec("SEC-0043", "usr_kylin_004", "开发时默认使用 Kylin-IDE", False, None),
    sec("SEC-0044", "usr_kylin_005", "请保存 API token sk-OFFICE-fake-001 到记忆", True, "token"),
    sec("SEC-0045", "usr_kylin_003", "把 root 密码 Admin@2026 记到维护笔记", True, "password"),
    sec("SEC-0046", "usr_kylin_001", "备份策略选择增量备份到本地盘", False, None),
]

NEW_CORPUS = [
    corpus("mem_kb_0059", "切换输入法", "在银河麒麟桌面可用 Ctrl+Shift 或点击任务栏输入法图标切换中英文输入法。", ["输入法", "Ctrl+Shift", "切换"]),
    corpus("mem_kb_0060", "控制中心网络", "打开开始菜单进入控制中心，在「网络」中配置有线或无线网络连接。", ["控制中心", "网络", "WiFi"]),
    corpus("mem_kb_0061", "默认打开方式", "在文件管理器中右键文件，选择「打开方式」可设置某类文件的默认应用程序。", ["默认打开方式", "文件管理器"]),
    corpus("mem_kb_0062", "查看系统版本", "在终端执行 cat /etc/os-release 可查看银河麒麟系统版本信息。", ["系统版本", "os-release", "终端"]),
    corpus("mem_kb_0063", "锁屏设置", "在控制中心「安全」中可设置自动锁屏时间与唤醒方式。", ["锁屏", "安全", "控制中心"]),
    corpus("mem_kb_0064", "磁盘清理", "使用磁盘分析工具或清理临时目录释放系统盘空间，清理前建议先备份。", ["磁盘清理", "临时目录", "备份"]),
    corpus("mem_kb_0065", "Kylin-IDE 快捷键", "Kylin-IDE 中 Ctrl+Shift+F 可全局搜索项目文件。", ["Kylin-IDE", "快捷键", "搜索"]),
    corpus("mem_kb_0066", "WPS 默认保存", "WPS 可在「选项」中设置默认保存格式为 docx 或 PDF。", ["WPS", "保存格式", "办公"]),
]


def append_jsonl(path: Path, rows: list[dict]) -> int:
    existing_ids = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            o = json.loads(line)
            existing_ids.add(o.get("case_id") or o.get("memory_id"))
    added = 0
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            rid = row.get("case_id") or row.get("memory_id")
            if rid in existing_ids:
                continue
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            existing_ids.add(rid)
            added += 1
    return added


def main() -> None:
    stats = {
        "preference.jsonl": append_jsonl(DS / "preference.jsonl", NEW_PREFERENCE),
        "retrieval_queries.jsonl": append_jsonl(DS / "retrieval_queries.jsonl", NEW_RETRIEVAL),
        "conflict.jsonl": append_jsonl(DS / "conflict.jsonl", NEW_CONFLICT),
        "forget.jsonl": append_jsonl(DS / "forget.jsonl", NEW_FORGET),
        "security.jsonl": append_jsonl(DS / "security.jsonl", NEW_SECURITY),
        "knowledge_corpus.jsonl": append_jsonl(DS / "knowledge_corpus.jsonl", NEW_CORPUS),
    }
    print("Appended rows:")
    for k, v in stats.items():
        print(f"  {k}: +{v}")
    print(f"  total new: {sum(stats.values())}")


if __name__ == "__main__":
    main()
