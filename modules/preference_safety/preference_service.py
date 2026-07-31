"""PreferenceService — 偏好提取、合并、查询、历史。

Implements V1.1 Protocol: extract, upsert, resolve, history
Based on C++ OSMemory::extractByRules / extractPreferenceSignals / recordBehavior
"""
from __future__ import annotations

from typing import Any

# ── 100 preference extraction rules (from C++ datasets/preference/rules.txt) ──
RULES: list[tuple[str, str, str, str, float]] = [
    # ui (20)
    ("深色", "theme", "dark", "ui", 0.90),
    ("暗色", "theme", "dark", "ui", 0.90),
    ("浅色", "theme", "light", "ui", 0.90),
    ("亮色", "theme", "light", "ui", 0.90),
    ("大字体", "font_size", "large", "ui", 0.80),
    ("小字体", "font_size", "small", "ui", 0.80),
    ("等宽字体", "font_mono", "yes", "ui", 0.70),
    ("大图标", "icon_size", "large", "ui", 0.75),
    ("列表视图", "file_view", "list", "ui", 0.70),
    ("图标视图", "file_view", "icon", "ui", 0.70),
    ("半透明", "transparency", "yes", "ui", 0.75),
    ("不透明", "transparency", "no", "ui", 0.75),
    ("动画", "animation", "enabled", "ui", 0.70),
    ("减少动画", "animation", "reduced", "ui", 0.80),
    ("24小时", "time_format", "24h", "ui", 0.85),
    ("12小时", "time_format", "12h", "ui", 0.85),
    ("高对比度", "high_contrast", "yes", "ui", 0.80),
    ("缩放比例", "display_scale", "150", "ui", 0.75),
    ("中文界面", "lang", "zh_CN", "ui", 0.90),
    ("英文界面", "lang", "en_US", "ui", 0.90),
    # tool (30)
    ("VS Code", "editor", "vscode", "tool", 0.85),
    ("vim", "editor", "vim", "tool", 0.85),
    ("Visual Studio", "editor", "vscode", "tool", 0.80),
    ("Neovim", "editor", "nvim", "tool", 0.85),
    ("Emacs", "editor", "emacs", "tool", 0.85),
    ("Sublime", "editor", "sublime", "tool", 0.85),
    ("WPS", "office", "wps", "tool", 0.80),
    ("LibreOffice", "office", "libreoffice", "tool", 0.80),
    ("Firefox", "browser", "firefox", "tool", 0.85),
    ("Chrome", "browser", "chrome", "tool", 0.85),
    ("Edge", "browser", "edge", "tool", 0.80),
    ("git", "vcs", "git", "tool", 0.90),
    ("docker", "container", "docker", "tool", 0.85),
    ("Podman", "container", "podman", "tool", 0.80),
    ("Python", "language", "python", "tool", 0.80),
    ("C++", "language", "cpp", "tool", 0.80),
    ("Java", "language", "java", "tool", 0.80),
    ("JavaScript", "language", "javascript", "tool", 0.80),
    ("Go", "language", "go", "tool", 0.80),
    ("Rust", "language", "rust", "tool", 0.80),
    ("cmake", "build_tool", "cmake", "tool", 0.85),
    ("GCC", "compiler", "gcc", "tool", 0.85),
    ("Clang", "compiler", "clang", "tool", 0.80),
    ("make", "build_tool", "make", "tool", 0.85),
    ("输入法", "input_method", "sogou", "tool", 0.80),
    ("搜狗", "input_method", "sogou", "tool", 0.80),
    ("MySQL", "database", "mysql", "tool", 0.85),
    ("PostgreSQL", "database", "postgresql", "tool", 0.85),
    ("Redis", "cache", "redis", "tool", 0.85),
    ("SSH终端", "ssh_client", "openssh", "tool", 0.80),
    # security (25)
    ("防火墙", "firewall", "enabled", "security", 0.85),
    ("自动锁屏", "auto_lock", "enabled", "security", 0.90),
    ("加密", "encryption", "enabled", "security", 0.90),
    ("双因素", "two_factor", "enabled", "security", 0.90),
    ("隐私", "privacy_mode", "enabled", "security", 0.85),
    ("SELinux", "selinux", "enforcing", "security", 0.85),
    ("AppArmor", "apparmor", "enabled", "security", 0.80),
    ("VPN连接", "vpn", "enabled", "security", 0.85),
    ("SSH密钥", "ssh_key", "yes", "security", 0.90),
    ("免密登录", "passwordless_login", "yes", "security", 0.85),
    ("密码管理器", "password_manager", "yes", "security", 0.80),
    ("生物识别", "biometric", "enabled", "security", 0.85),
    ("指纹登录", "fingerprint", "enabled", "security", 0.85),
    ("全盘加密", "full_disk_encryption", "yes", "security", 0.90),
    ("自动锁屏时间", "auto_lock_timeout", "300", "security", 0.80),
    ("登录失败锁定", "login_lockout", "enabled", "security", 0.85),
    ("端口扫描防护", "port_scan_protection", "yes", "security", 0.80),
    ("入侵检测", "intrusion_detection", "enabled", "security", 0.80),
    ("安全审计", "audit_logging", "enabled", "security", 0.85),
    ("非root用户", "non_root_user", "yes", "security", 0.85),
    ("沙箱隔离", "sandbox", "enabled", "security", 0.85),
    ("最小权限", "least_privilege", "yes", "security", 0.80),
    ("内核加固", "kernel_hardening", "enabled", "security", 0.80),
    ("安全更新", "security_updates", "auto", "security", 0.90),
    ("日志监控", "log_monitoring", "enabled", "security", 0.85),
    # workflow (25)
    ("快捷键", "use_shortcuts", "yes", "workflow", 0.75),
    ("定期备份", "auto_backup", "enabled", "workflow", 0.85),
    ("免打扰", "dnd", "enabled", "workflow", 0.85),
    ("云端同步", "cloud_sync", "enabled", "workflow", 0.80),
    ("自动更新", "auto_update", "enabled", "workflow", 0.85),
    ("多桌面", "multi_desktop", "yes", "workflow", 0.80),
    ("通知", "notifications", "enabled", "workflow", 0.70),
    ("静音", "sound_mute", "yes", "workflow", 0.75),
    ("夜间模式", "night_mode", "enabled", "workflow", 0.80),
    ("定时关机", "scheduled_shutdown", "enabled", "workflow", 0.75),
    ("按名称排序", "file_sort", "name", "workflow", 0.75),
    ("按时间排序", "file_sort", "time", "workflow", 0.75),
    ("按大小排序", "file_sort", "size", "workflow", 0.75),
    ("增量备份", "backup_type", "incremental", "workflow", 0.80),
    ("全量备份", "backup_type", "full", "workflow", 0.80),
    ("云备份", "backup_target", "cloud", "workflow", 0.85),
    ("本地备份", "backup_target", "local", "workflow", 0.80),
    ("自动保存", "auto_save", "enabled", "workflow", 0.80),
    ("标签页", "tabbed_ui", "yes", "workflow", 0.70),
    ("分屏", "split_view", "yes", "workflow", 0.75),
    ("终端复用", "terminal_multiplexer", "tmux", "workflow", 0.80),
    ("代理设置", "proxy", "enabled", "workflow", 0.75),
    ("静态IP", "ip_config", "static", "workflow", 0.80),
    ("DHCP", "ip_config", "dhcp", "workflow", 0.80),
    ("消息提醒", "desktop_alerts", "enabled", "workflow", 0.70),
]


def _normalize_text(text: str) -> str:
    """Remove spaces between CJK characters for better matching."""
    result = []
    i = 0
    while i < len(text):
        b = text[i].encode("utf-8", errors="ignore")
        if len(b) >= 3 and i + 3 < len(text) and text[i + 3] == " ":
            # CJK char followed by space, check if next char is also CJK
            nc = text[i + 4].encode("utf-8", errors="ignore") if i + 4 < len(text) else b""
            if len(nc) >= 3:
                result.append(text[i : i + 3])
                i += 4
                continue
        result.append(text[i])
        i += 1
    return "".join(result)


class PreferenceService:
    def __init__(self):
        self._preferences: dict[str, dict] = {}   # key -> current value
        self._history: dict[str, list[dict]] = {}  # key -> versions
        self._rules = RULES

    # ── extract ───────────────────────────────────────────────

    def extract(self, events: list[dict]) -> list[dict]:
        candidates = []
        for event in events:
            text = event.get("text", event.get("content_text", "")) or \
                   str(event.get("payload", event.get("body", "")))
            if not text:
                continue
            user_id = event.get("user_id", "default")
            scene = event.get("scene", "default")
            for kw, key, val, cat, cf in self._rules:
                if kw in text or kw in _normalize_text(text) or kw in text.upper():
                    candidates.append({
                        "preference_key": key,
                        "value": val,
                        "category": cat,
                        "confidence": cf,
                        "user_id": user_id,
                        "scene": scene,
                        "source_event_id": event.get("source_event_id", event.get("request_id", "")),
                        "scope": "global",
                    })
        return candidates

    # ── upsert ────────────────────────────────────────────────

    def upsert(self, candidates: list[dict]) -> list[dict]:
        records = []
        for c in candidates:
            key = c["preference_key"]
            val = c["value"]
            if key in self._preferences:
                old = self._preferences[key]
                if old["value"] == val:
                    old["confidence"] = max(old["confidence"], c["confidence"])
                    old["evidence_count"] += 1
                    old["evidence"].append({
                        "source_event_id": c.get("source_event_id", ""),
                        "weight": c["confidence"],
                    })
                    records.append(old)
                    continue
                old["revision"] += 1
                old["value"] = val
                old["confidence"] = c["confidence"]
                old["evidence"].append({
                    "source_event_id": c.get("source_event_id", ""),
                    "weight": c["confidence"],
                })
                old["evidence_count"] = len(old["evidence"])
                self._history.setdefault(key, []).append(dict(old))
                records.append(old)
            else:
                rec = {
                    "preference_key": key,
                    "value": val,
                    "category": c["category"],
                    "scope": c.get("scope", "global"),
                    "scope_value": c.get("scene", c.get("scope_value", "")),
                    "polarity": c.get("polarity", "positive"),
                    "confidence": c["confidence"],
                    "evidence_count": 1,
                    "evidence": [{"source_event_id": c.get("source_event_id", ""), "weight": c["confidence"]}],
                    "revision": 1,
                    "status": "active",
                }
                self._preferences[key] = rec
                self._history.setdefault(key, []).append(dict(rec))
                records.append(rec)
        return records

    # ── resolve ───────────────────────────────────────────────

    def resolve(self, user_id: str = "", scene: str = "",
                keys: list[str] | None = None) -> list[dict]:
        results = []
        for k, p in self._preferences.items():
            if keys and k not in keys:
                continue
            if p["status"] == "active":
                results.append(dict(p))
        return results

    # ── history ───────────────────────────────────────────────

    def history(self, user_id: str = "", preference_key: str = "") -> list[dict]:
        if preference_key not in self._history:
            return []
        return list(self._history[preference_key])
