"""Contract-aligned preference extraction over the frozen V1.1 rules.

The donor rule file remains immutable.  This module normalizes its legacy key
space and adds context-sensitive rules needed by the V1.2.2 preference schema.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_TEMPORARY_CUES = (
    "临时",
    "这次",
    "本次",
    "这一小时",
    "这一会",
    "仅本轮",
    "下次不用管",
    "不用记",
    "不要记住",
)

_LEGACY_KEY_MAP = {
    "theme": "ui.theme",
    "font_size": "ui.font_size",
    "font_mono": "ui.font_mono",
    "icon_size": "ui.icon_size",
    "file_view": "files.view",
    "transparency": "ui.transparency",
    "animation": "ui.animation",
    "time_format": "ui.time_format",
    "high_contrast": "ui.high_contrast",
    "display_scale": "ui.display_scale",
    "lang": "ui.language",
    "editor": "tool.editor",
    "office": "tool.office",
    "browser": "tool.browser",
    "vcs": "tool.vcs",
    "container": "tool.container",
    "language": "tool.language",
    "build_tool": "tool.build_tool",
    "compiler": "tool.compiler",
    "input_method": "tool.input_method",
    "database": "tool.database",
    "cache": "tool.cache",
    "ssh_client": "tool.ssh_client",
    "firewall": "security.firewall",
    "auto_lock": "security.auto_lock",
    "selinux": "security.selinux",
    "dnd": "ui.dnd",
    "notifications": "ui.notifications",
    "file_sort": "files.sort",
    "backup_type": "workflow.backup",
    "backup_target": "workflow.backup_target",
    "auto_update": "workflow.updates",
    "proxy": "network.proxy",
}

_VALUE_MAP = {
    ("ui.high_contrast", "yes"): "enabled",
    ("files.sort", "time"): "mtime",
}


def enhance_candidates(
    events: list[Mapping[str, Any]],
    legacy_candidates: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return canonical candidates while retaining broad V1.1 coverage."""
    candidates_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for candidate in legacy_candidates:
        source_event_id = str(candidate.get("source_event_id", ""))
        candidates_by_event.setdefault(source_event_id, []).append(candidate)

    enhanced: list[dict[str, Any]] = []
    for event in events:
        text = str(event.get("text", ""))
        if not text or _is_temporary_instruction(text):
            continue
        source_event_id = str(event.get("source_event_id", ""))
        specific = _extract_contextual(event, text)
        contextual_keys = {
            str(candidate["preference_key"]) for candidate in specific
        }
        combined = list(specific)
        for raw in candidates_by_event.get(source_event_id, []):
            candidate = _canonicalize_legacy(raw)
            key = str(candidate["preference_key"])
            if key in contextual_keys:
                continue
            if _suppressed_legacy_candidate(text, key, contextual_keys):
                continue
            combined.append(candidate)
        enhanced.extend(_deduplicate(combined))
    return enhanced


def _extract_contextual(
    event: Mapping[str, Any],
    text: str,
) -> list[dict[str, Any]]:
    lower = text.casefold()
    found: list[dict[str, Any]] = []

    def add(
        key: str,
        value: Any,
        category: str,
        *,
        scope: str = "global",
        scope_value: str = "global",
        confidence: float = 0.88,
    ) -> None:
        found.append(
            {
                "preference_key": key,
                "value": value,
                "category": category,
                "confidence": confidence,
                "user_id": event.get("user_id", "default"),
                "scene": event.get("scene", "default"),
                "source_event_id": event.get("source_event_id", ""),
                "scope": scope,
                "scope_value": scope_value,
                "polarity": "positive",
            }
        )

    if "完整" in text and ("目录结构" in text or "代码目录" in text):
        add("output.structure", "complete_tree", "output_style")
    if "完整" in text and "可运行" in text and (
        "示例" in text or "代码" in text
    ):
        add("output.code_example", "full_runnable", "output_style")
    if "kylin-ide" in lower or "麒麟ide" in lower:
        add("tool.editor", "kylin_ide", "tool_choice")

    if "减少" in text and "动画" in text:
        add("ui.animation", "reduced", "operation_habit")
    if "高对比度" in text:
        add("ui.high_contrast", "enabled", "operation_habit")
    if "免打扰" in text:
        add("ui.dnd", "enabled", "operation_habit")
    if "终端" in text and _contains_any(text, ("深色", "暗色")):
        add("ui.terminal_theme", "dark", "operation_habit")
    elif _contains_any(text, ("深色主题", "暗色主题")):
        add("ui.theme", "dark", "operation_habit")
    elif _contains_any(text, ("浅色主题", "亮色主题")):
        add("ui.theme", "light", "operation_habit")

    if "排序" in text and _contains_any(text, ("修改时间", "按时间")):
        add("files.sort", "mtime", "operation_habit")
    if "结论" in text and _contains_any(text, ("表格", "附表")):
        add(
            "output.structure",
            "conclusion_then_table",
            "output_style",
        )
    if "markdown" in lower and _contains_any(
        text,
        ("输出", "周报", "格式", "结论"),
    ):
        add("output.format", "markdown", "output_style")
    if "pdf" in lower and "导出" in text:
        add("output.export", "pdf", "output_style")

    lock_seconds = re.search(r"(?:自动)?锁屏[^\d]{0,12}(\d+)\s*秒", text)
    if lock_seconds:
        add(
            "security.auto_lock",
            lock_seconds.group(1),
            "safety_policy",
        )
    if "明文" in text and _contains_any(text, ("密码", "口令", "密钥")) and _contains_any(
        text,
        ("禁止", "不允许", "不得"),
    ):
        add(
            "security.store_plaintext_secret",
            "forbidden",
            "safety_policy",
        )
    if "ssh" in lower and "密钥" in text and _contains_any(
        text,
        ("仅允许", "只允许", "仅使用", "只使用"),
    ):
        add("security.ssh_auth", "pubkey_only", "safety_policy")

    if "备份" in text and _contains_any(text, ("成功", "完成")) and _contains_any(
        text,
        ("任务", "执行", "日志"),
    ):
        add(
            "workflow.backup_last_status",
            "success",
            "operation_habit",
        )
    elif "增量备份" in text and _contains_any(
        text,
        ("本地", "本地盘", "本机"),
    ):
        add(
            "workflow.backup",
            "incremental_local",
            "operation_habit",
        )
    if "更新" in text and _contains_any(text, ("手动确认", "手动批准")):
        add("workflow.updates", "manual", "operation_habit")
    if "有线" in text and _contains_any(text, ("网络", "连接")):
        add("network.prefer", "ethernet", "operation_habit")

    scene = str(event.get("scene", "default"))
    if "代理" in text and _contains_any(text, ("公司", "企业", "单位")):
        add(
            "network.proxy",
            "corp_http",
            "operation_habit",
            scope="scene",
            scope_value=scene,
        )
    elif "代理" in text and _contains_any(text, ("关闭", "直连", "不使用")):
        add(
            "network.proxy",
            "direct",
            "operation_habit",
            scope="scene",
            scope_value=scene,
        )
    if "调试" in text and "端口" in text and _contains_any(
        text,
        ("禁用", "禁止", "关闭"),
    ):
        add(
            "security.debug_port",
            "disabled",
            "safety_policy",
            scope="scene",
            scope_value=scene,
        )
    else:
        debug_port = re.search(r"(\d{2,5})\s*(?:端口)?\s*调试", text)
        if debug_port:
            add(
                "security.debug_port",
                debug_port.group(1),
                "safety_policy",
                scope="scene",
                scope_value=scene,
            )

    return found


def _canonicalize_legacy(raw: Mapping[str, Any]) -> dict[str, Any]:
    candidate = dict(raw)
    old_key = str(candidate.get("preference_key", ""))
    key = _LEGACY_KEY_MAP.get(old_key, old_key)
    candidate["preference_key"] = key
    candidate["category"] = _category_for_key(
        key,
        str(candidate.get("category", "operation_habit")),
    )
    candidate["value"] = _VALUE_MAP.get(
        (key, str(candidate.get("value"))),
        candidate.get("value"),
    )
    candidate.setdefault("scope", "global")
    candidate.setdefault("scope_value", "global")
    candidate.setdefault("polarity", "positive")
    return candidate


def _category_for_key(key: str, fallback: str) -> str:
    if key.startswith(("output.",)):
        return "output_style"
    if key.startswith("tool."):
        return "tool_choice"
    if key.startswith("security."):
        return "safety_policy"
    if key.startswith(("ui.", "files.", "workflow.", "network.")):
        return "operation_habit"
    return fallback


def _suppressed_legacy_candidate(
    text: str,
    key: str,
    contextual_keys: set[str],
) -> bool:
    if key == "ui.notifications" and "ui.dnd" in contextual_keys:
        return True
    if key == "ui.theme" and "ui.terminal_theme" in contextual_keys:
        return True
    if key == "workflow.backup" and (
        "workflow.backup_last_status" in contextual_keys
    ):
        return True
    if key == "workflow.backup_target" and "workflow.backup" in contextual_keys:
        return True
    if key == "ui.animation" and "减少" in text and "动画" in text:
        return True
    return False


def _deduplicate(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []
    for candidate in candidates:
        identity = (
            str(candidate.get("preference_key")),
            str(candidate.get("scope", "global")),
            str(candidate.get("scope_value", "global")),
        )
        if identity not in selected:
            order.append(identity)
            selected[identity] = candidate
    return [selected[identity] for identity in order]


def _is_temporary_instruction(text: str) -> bool:
    return any(cue in text for cue in _TEMPORARY_CUES)


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)
