"""Contract-aligned preference extraction over the frozen V1.1 rules.

The donor rule file remains immutable.  This module normalizes its legacy key
space and adds context-sensitive rules needed by the V1.2.2 preference schema.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


_TEMPORARY_CUES = (
    "临时",
    "这次",
    "本次",
    "这一小时",
    "这一会",
    "仅本轮",
    "只要这一次",
    "仅这一次",
    "这一回",
    "本轮",
    "暂时",
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
    "input_method": "tool.ime",
    "database": "tool.database",
    "cache": "tool.cache",
    "ssh_client": "tool.ssh_client",
    "firewall": "security.firewall",
    "auto_lock": "security.auto_lock",
    "encryption": "security.encryption",
    "two_factor": "security.two_factor",
    "privacy_mode": "security.privacy_mode",
    "selinux": "security.selinux",
    "apparmor": "security.apparmor",
    "vpn": "security.vpn",
    "ssh_key": "security.ssh_key",
    "passwordless_login": "security.passwordless_login",
    "password_manager": "security.password_manager",
    "biometric": "security.biometric",
    "fingerprint": "security.fingerprint",
    "full_disk_encryption": "security.full_disk_encryption",
    "auto_lock_timeout": "security.auto_lock_timeout",
    "login_lockout": "security.login_lockout",
    "port_scan_protection": "security.port_scan_protection",
    "intrusion_detection": "security.intrusion_detection",
    "audit_logging": "security.audit_log",
    "non_root_user": "security.non_root_user",
    "sandbox": "security.sandbox",
    "least_privilege": "security.least_privilege",
    "kernel_hardening": "security.kernel_hardening",
    "security_updates": "security.updates",
    "log_monitoring": "security.log_monitoring",
    "use_shortcuts": "ui.shortcuts",
    "dnd": "ui.dnd",
    "notifications": "ui.notifications",
    "multi_desktop": "ui.multi_desktop",
    "sound_mute": "ui.sound_mute",
    "night_mode": "ui.night_mode",
    "tabbed_ui": "ui.tabs",
    "split_view": "ui.split_view",
    "desktop_alerts": "ui.desktop_alerts",
    "file_sort": "files.sort",
    "auto_backup": "workflow.auto_backup",
    "backup_type": "workflow.backup",
    "backup_target": "workflow.backup_target",
    "auto_update": "workflow.updates",
    "cloud_sync": "workflow.cloud_sync",
    "scheduled_shutdown": "workflow.shutdown",
    "auto_save": "workflow.auto_save",
    "terminal_multiplexer": "tool.terminal_multiplexer",
    "proxy": "network.proxy",
    "ip_config": "network.ip_config",
}

_VALUE_MAP = {
    ("ui.high_contrast", "yes"): "enabled",
    ("files.sort", "time"): "mtime",
    ("ui.multi_desktop", "yes"): "enabled",
    ("security.full_disk_encryption", "yes"): "enabled",
}


@dataclass(frozen=True)
class _SignalRule:
    key: str
    value: str
    category: str
    patterns: tuple[str, ...]
    cues: tuple[str, ...]
    confidence: float = 0.88

    def matches(self, text: str) -> bool:
        return any(
            re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            for pattern in self.patterns
        )


_SIGNAL_RULES = (
    _SignalRule(
        "output.language",
        "zh_bullet",
        "output_style",
        (
            r"(?=.*(?:中文|汉语))(?=.*(?:条目|分点|列表|要点|项目符号))",
        ),
        ("中文", "汉语", "条目", "分点", "列表", "要点"),
    ),
    _SignalRule(
        "output.verbosity",
        "concise",
        "output_style",
        (
            r"(?:尽量|保持|回答|回复|输出)?.{0,6}(?:简短|简洁|精简|精炼)",
            r"(?:只要|直接给|仅给).{0,4}(?:结论|结果|答案)",
        ),
        ("简短", "简洁", "精简", "精炼", "只要结论", "直接给结论"),
    ),
    _SignalRule(
        "output.verbosity",
        "step_by_step",
        "output_style",
        (
            r"(?=.*(?:详细|逐步|一步一步|一步步))(?=.*(?:步骤|说明|讲解|分析|过程))",
            r"按(?:操作)?步骤.{0,8}(?:说明|讲解|回答|展开)",
        ),
        ("详细", "逐步", "一步一步", "一步步", "按步骤"),
    ),
    _SignalRule(
        "ui.multi_desktop",
        "enabled",
        "operation_habit",
        (r"(?:多桌面|多个(?:虚拟)?桌面|多个工作区|虚拟桌面)",),
        ("多桌面", "多个桌面", "多个工作区", "虚拟桌面"),
    ),
    _SignalRule(
        "ui.shortcuts",
        "custom_set_a",
        "operation_habit",
        (
            r"(?:快捷键|热键).{0,12}(?:方案|配置|集合|组合)?\s*[aａ](?:\b|组|套)",
        ),
        ("快捷键", "热键"),
    ),
    _SignalRule(
        "security.audit_log",
        "enabled",
        "safety_policy",
        (
            r"(?:开启|启用|打开|保留|记录).{0,8}(?:安全)?审计(?:日志|记录)?",
            r"(?:安全)?审计(?:日志|记录)?.{0,8}(?:开启|启用|打开|保留)",
        ),
        ("审计", "审计日志", "安全审计"),
    ),
    _SignalRule(
        "security.full_disk_encryption",
        "enabled",
        "safety_policy",
        (
            r"(?:启用|开启|打开|必须|要求|默认)?.{0,8}(?:全盘|整盘|系统盘|磁盘).{0,4}加密",
        ),
        ("全盘加密", "整盘加密", "系统盘加密", "磁盘加密"),
    ),
)


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

    for rule in _SIGNAL_RULES:
        if rule.matches(text) and not _is_negated_signal(text, rule.cues):
            add(
                rule.key,
                rule.value,
                rule.category,
                confidence=rule.confidence,
            )

    package_manager = _package_manager(text)
    if package_manager is not None:
        add("tool.package_manager", package_manager, "tool_choice")

    log_level = _log_level(text)
    if log_level is not None:
        add("workflow.log_level", log_level, "operation_habit")

    shutdown = _scheduled_shutdown(text)
    if shutdown is not None:
        add("workflow.shutdown", shutdown, "operation_habit")

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
    if (
        "终端" in text
        and _contains_any(text, ("深色", "暗色"))
        and not _is_negated_signal(text, ("深色", "暗色"))
    ):
        add("ui.terminal_theme", "dark", "operation_habit")
    elif _contains_any(text, ("深色主题", "暗色主题")) and not _is_negated_signal(
        text,
        ("深色主题", "暗色主题"),
    ):
        add("ui.theme", "dark", "operation_habit")
    elif _contains_any(text, ("浅色主题", "亮色主题")) and not _is_negated_signal(
        text,
        ("浅色主题", "亮色主题"),
    ):
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


_LEGACY_KEY_CUES = {
    "ui.theme": ("深色", "暗色", "浅色", "亮色"),
    "ui.animation": ("动画",),
    "ui.multi_desktop": ("多桌面", "多个桌面", "多个工作区"),
    "ui.shortcuts": ("快捷键", "热键"),
    "security.audit_log": ("审计", "审计日志", "安全审计"),
    "security.full_disk_encryption": (
        "全盘加密",
        "整盘加密",
        "系统盘加密",
        "磁盘加密",
    ),
}


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
    if (
        key == "security.encryption"
        and "security.full_disk_encryption" in contextual_keys
    ):
        return True
    cues = _LEGACY_KEY_CUES.get(key)
    if cues is not None and _is_negated_signal(text, cues):
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
    if any(cue in text for cue in _TEMPORARY_CUES):
        return True
    return bool(
        re.search(
            r"(?:只|仅)(?:要)?(?:这|本)(?:一)?(?:次|轮)",
            text,
        )
    )


def _is_negated_signal(text: str, cues: tuple[str, ...]) -> bool:
    for cue in cues:
        start = text.find(cue)
        while start >= 0:
            prefix = text[max(0, start - 12) : start]
            if re.search(
                r"(?:不要|不再|不需|不使用|不喜欢|不启用|不开启|"
                r"别|避免|取消|关闭|禁用|禁止)\s*.{0,5}$",
                prefix,
            ):
                return True
            start = text.find(cue, start + len(cue))
    return False


def _package_manager(text: str) -> str | None:
    lower = text.casefold()
    if not _contains_any(
        lower,
        ("包管理", "软件包", "依赖", "默认", "优先", "首选"),
    ):
        return None
    for manager in ("apt", "dnf", "yum", "zypper", "pacman"):
        if re.search(rf"(?<![\w-]){manager}(?![\w-])", lower) and not _is_negated_signal(
            lower,
            (manager,),
        ):
            return manager
    return None


def _log_level(text: str) -> str | None:
    lower = text.casefold()
    patterns = (
        r"(?:日志(?:记录)?(?:级别|等级)|log\s*level).{0,10}"
        r"(debug|info|warn(?:ing)?|error)",
        r"(debug|info|warn(?:ing)?|error).{0,10}"
        r"(?:日志(?:记录)?(?:级别|等级)|log\s*level)",
    )
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            value = match.group(1)
            return "warning" if value in {"warn", "warning"} else value
    return None


def _scheduled_shutdown(text: str) -> str | None:
    if not _contains_any(text, ("关机", "自动关机", "定时关机")):
        return None
    if not _contains_any(text, ("工作日", "周一至周五", "周一到周五")):
        return None
    if _is_negated_signal(text, ("关机", "自动关机", "定时关机")):
        return None

    numeric = re.search(
        r"(上午|下午|傍晚|晚上|夜间)?\s*([01]?\d|2[0-3])"
        r"\s*(?::\s*\d{2}|点)",
        text,
    )
    if numeric:
        period, raw_hour = numeric.groups()
        hour = int(raw_hour)
        if period in {"下午", "傍晚", "晚上", "夜间"} and hour < 12:
            hour += 12
        return f"weekday_{hour:02d}"

    chinese = re.search(
        r"(上午|下午|傍晚|晚上|夜间)?\s*"
        r"([一二三四五六七八九十]{1,3})点",
        text,
    )
    if chinese:
        period, raw_hour = chinese.groups()
        hour = _chinese_hour(raw_hour)
        if hour is not None:
            if period in {"下午", "傍晚", "晚上", "夜间"} and hour < 12:
                hour += 12
            return f"weekday_{hour:02d}"
    return None


def _chinese_hour(value: str) -> int | None:
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
    if value == "十":
        return 10
    if "十" in value:
        tens, ones = value.split("十", 1)
        return digits.get(tens, 1) * 10 + digits.get(ones, 0)
    return digits.get(value)


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)
