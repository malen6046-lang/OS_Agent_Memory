# -*- coding: utf-8 -*-
"""Expand each evaluation task to a target size (dev only; validation/final_test frozen).

Idempotent: skips case_ids / memory_ids that already exist.
Usage:
  python scripts/expand_dataset_to_500.py
  python scripts/expand_dataset_to_500.py --target 820
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "evaluation" / "dataset"
TARGET = 820
SCALE_TAG = "v0.5_scale"

USERS = [f"usr_kylin_{i:03d}" for i in range(1, 6)]
SHARED = "usr_corpus_shared"
SCENES = [
    "software_dev",
    "office_automation",
    "system_maintenance",
    "galaxy_kylin_v11",
    "desktop",
    "security",
]

PROV = {
    "preference": {
        "inspired_by": "LaMP user-history-to-preference format",
        "license_note": "仅借鉴任务结构；样本为原创麒麟OS场景",
        "adaptation": "V0.5 scale expand; fields align V1.2.1/V1.2.2",
    },
    "retrieval": {
        "inspired_by": "BEIR corpus-query-qrels format",
        "license_note": "仅借鉴评测思想；知识为原创",
        "adaptation": "V0.5 scale expand",
    },
    "conflict": {
        "inspired_by": "SNLI/MNLI relation labels mapped to OS conflict",
        "license_note": "样本原创",
        "adaptation": "V0.5 scale expand; ConflictDecision enums",
    },
    "forget": {
        "inspired_by": "TOFU forget-request and residual evaluation",
        "license_note": "样本原创",
        "adaptation": "V0.5 scale expand; semantic fixtures",
    },
    "security": {
        "inspired_by": "TOFU/unlearning + safety filter practice",
        "license_note": "假数据；样本原创",
        "adaptation": "V0.5 scale expand",
    },
}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path: Path, rows: list[dict]) -> int:
    if not rows:
        return 0
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def max_num(ids: set[str], prefix: str) -> int:
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    n = 0
    for i in ids:
        m = pat.match(i)
        if m:
            n = max(n, int(m.group(1)))
    return n


def max_kb(ids: set[str]) -> int:
    pat = re.compile(r"^mem_kb_(\d+)$")
    n = 0
    for i in ids:
        m = pat.match(i)
        if m:
            n = max(n, int(m.group(1)))
    return n


# ---------- preference catalog ----------
PREF_CATALOG = [
    ("output.structure", "complete_tree", "output_style", "要求输出完整代码目录结构", "用户连续要求输出完整代码目录结构"),
    ("output.structure", "conclusion_first", "output_style", "纪要先写结论", "会议纪要要求先列结论再展开"),
    ("output.format", "markdown", "output_style", "输出用 Markdown", "周报与说明默认使用 Markdown 输出"),
    ("output.format", "pdf", "output_style", "导出为 PDF", "文档导出格式设为 PDF"),
    ("output.verbosity", "concise", "output_style", "回答尽量简短", "回答只要结论，尽量简短"),
    ("output.verbosity", "step_by_step", "output_style", "逐步详细说明", "安装与排障要求逐步详细说明"),
    ("output.comment_language", "zh", "output_style", "注释用中文", "代码注释默认使用中文"),
    ("output.language", "zh_bullet", "output_style", "中文条目列出", "审查意见用中文条目列出"),
    ("tool.editor", "kylin_ide", "tool_choice", "默认 Kylin-IDE", "开发时默认使用 Kylin-IDE 打开工程"),
    ("tool.editor", "vim", "tool_choice", "用 vim 编辑", "用户习惯用 vim 编辑配置文件"),
    ("tool.editor", "vscode", "tool_choice", "用 VS Code", "本地调试常用 VS Code"),
    ("tool.office", "wps", "tool_choice", "办公用 WPS", "办公文档统一使用 WPS 打开"),
    ("tool.office", "libreoffice", "tool_choice", "用 LibreOffice", "表格编辑优先 LibreOffice"),
    ("tool.browser", "firefox", "tool_choice", "默认 Firefox", "浏览器默认使用 Firefox"),
    ("tool.browser", "chrome", "tool_choice", "默认 Chrome", "默认浏览器改为 Chrome"),
    ("tool.compiler", "gcc", "tool_choice", "编译器用 gcc", "构建日志显示使用 gcc 完成编译"),
    ("tool.container", "podman", "tool_choice", "容器用 Podman", "容器工具选择 Podman 而非 Docker"),
    ("tool.vcs", "git", "tool_choice", "版本管理用 git", "版本管理默认使用 git"),
    ("tool.ime", "sogou", "tool_choice", "输入法搜狗", "输入法切换为搜狗拼音"),
    ("tool.package_manager", "apt", "tool_choice", "包管理 apt", "包管理优先使用 apt"),
    ("ui.theme", "dark", "operation_habit", "深色主题", "用户喜欢深色主题界面"),
    ("ui.theme", "light", "operation_habit", "浅色主题", "用户切换到浅色主题并保存"),
    ("ui.font_size", "large", "operation_habit", "大字体", "设置大字体以便阅读文档"),
    ("ui.animation", "reduced", "operation_habit", "减少动画", "减少桌面动画效果"),
    ("ui.dnd", "enabled", "operation_habit", "免打扰", "通知设置为免打扰"),
    ("files.sort", "mtime", "operation_habit", "按修改时间排序", "文件默认按修改时间排序"),
    ("workflow.backup", "incremental_local", "operation_habit", "增量本地备份", "备份策略选择增量备份到本地盘"),
    ("workflow.backup", "full_local", "operation_habit", "全量本地备份", "周末执行全量本地备份"),
    ("workflow.updates", "manual", "operation_habit", "更新手动确认", "软件更新设置为手动确认"),
    ("network.prefer", "ethernet", "operation_habit", "优先有线", "网络优先使用有线连接"),
    ("network.proxy", "corp_http", "operation_habit", "公司代理", "交付场景使用公司 HTTP 代理"),
    ("network.proxy", "direct", "operation_habit", "直连", "个人场景关闭代理直连"),
    ("logging.level", "info", "operation_habit", "日志 INFO", "日志级别默认设为 INFO"),
    ("cleanup.priority", "temp_dirs_first", "operation_habit", "先清缓存", "清理磁盘时优先清理缓存目录"),
    ("security.auto_lock", "300", "safety_policy", "锁屏 300 秒", "启用自动锁屏，超时 300 秒"),
    ("security.firewall", "enabled", "safety_policy", "开启防火墙", "开启系统防火墙"),
    ("security.firewall", "disabled", "safety_policy", "关闭防火墙", "调试环境关闭防火墙以便联调"),
    ("security.ssh_auth", "pubkey_only", "safety_policy", "SSH 仅密钥", "SSH 仅允许密钥登录"),
    ("security.selinux", "enforcing", "safety_policy", "SELinux enforcing", "SELinux 设置为 enforcing"),
    ("security.store_plaintext_secret", "forbidden", "safety_policy", "禁止明文密码入库", "禁止将明文密码写入记忆"),
    ("security.debug_port", "disabled", "safety_policy", "禁用调试端口", "交付场景禁用调试端口"),
    ("security.debug_port", "8080", "safety_policy", "允许 8080", "个人场景允许本地 8080 调试"),
    ("security.audit_log", "enabled", "safety_policy", "审计日志开启", "安全审计日志保持开启"),
    ("input.method", "sogou_pinyin", "tool_choice", "搜狗拼音", "默认输入法使用搜狗拼音"),
]

EPHEMERAL = [
    ("这次回答请用英文，以后还是中文", "output.language=en"),
    ("仅本次导出 PDF，平时仍用 Markdown", "output.format=pdf_once"),
    ("临时用 vim 改这一个文件，别改默认 IDE", "tool.editor=vim_once"),
    ("演示这一小时先关掉自动锁屏", "security.auto_lock=disabled"),
    ("只要这一次用表格展示，下次不用管", "output.format=table"),
    ("本次会议临时关闭防火墙，会后恢复", "security.firewall=disabled_once"),
]


def make_pref_row(n: int, key: str, val: str, cat: str, text: str, *, ephemeral: bool = False, eph: str | None = None) -> dict:
    cid = f"PREF-{n:04d}"
    uid = USERS[n % len(USERS)]
    scene = SCENES[n % len(SCENES)]
    source = ["user_behavior", "manual_config", "tool_result", "cross_scene"][n % 4]
    evt = f"evt_pref_{n:04d}"
    prefs = []
    if not ephemeral:
        prefs = [
            {
                "preference_key": key,
                "value": val,
                "category": cat,
                "scope": "global",
                "scope_value": "global",
                "polarity": "positive",
                "confidence": 0.88,
                "evidence_count": 1,
                "evidence": [{"source_event_id": evt, "weight": 0.8}],
                "revision": 1,
                "status": "active",
            }
        ]
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
                "request_id": f"req_pref_{n:04d}",
                "idempotency_key": f"idem_pref_{n:04d}",
                "user_id": uid,
                "session_id": None,
                "scene": scene,
                "source": source,
                "source_event_id": evt,
                "occurred_at": "2026-08-25T10:00:00+08:00",
                "payload": {"text": text if not ephemeral else text},
            }
        ],
        "expected": {"preferences": prefs, "is_ephemeral_instruction": ephemeral},
        "evaluation": {
            "primary_metric": "preference_exact_match",
            "also_report": ["macro_f1", "ephemeral_false_positive_rate"],
        },
        "tags": ["银河麒麟V11", "中文", SCALE_TAG, cat if not ephemeral else "ephemeral"],
        "provenance": PROV["preference"],
        "quality": {"generation": "v0.5_scale_expand", "human_reviewed": False},
    }
    if ephemeral and eph:
        row["expected"]["ephemeral_text"] = eph
    # diversify wording with index
    if not ephemeral:
        variants = [
            text,
            f"用户明确设置：{text}",
            f"配置已保存：{text}",
            f"最近多次操作显示：{text}",
            f"在麒麟桌面场景下，{text}",
        ]
        row["input_events"][0]["payload"]["text"] = variants[n % len(variants)]
    return row


# ---------- corpus / retrieval ----------
CORPUS_TOPICS = [
    ("打开终端", "workflow", "在银河麒麟桌面按 Ctrl+Alt+T 或从开始菜单搜索“终端”打开。", ["终端", "Ctrl+Alt+T"]),
    ("软件商店安装", "workflow", "打开麒麟应用商店，搜索应用名称后点击安装并确认权限。", ["软件商店", "安装"]),
    ("检查网络", "workflow", "在控制中心检查有线/无线连接，必要时用 ping 测试网关。", ["网络", "ping"]),
    ("查看系统版本", "fact", "在终端执行 cat /etc/os-release 查看银河麒麟版本信息。", ["系统版本", "os-release"]),
    ("切换输入法", "workflow", "可用 Ctrl+Shift 或点击任务栏输入法图标切换中英文。", ["输入法", "Ctrl+Shift"]),
    ("控制中心网络", "workflow", "开始菜单进入控制中心，在「网络」中配置有线或无线。", ["控制中心", "网络"]),
    ("默认打开方式", "workflow", "文件管理器右键文件，选择「打开方式」设置默认应用。", ["打开方式", "文件管理器"]),
    ("锁屏设置", "security_policy", "控制中心「安全」中可设置自动锁屏时间与唤醒方式。", ["锁屏", "安全"]),
    ("磁盘清理", "workflow", "清理临时目录前建议先备份；可用磁盘分析工具释放空间。", ["磁盘清理", "临时目录"]),
    ("Kylin-IDE 搜索", "workflow", "Kylin-IDE 中 Ctrl+Shift+F 可全局搜索项目文件。", ["Kylin-IDE", "搜索"]),
    ("WPS 保存格式", "operation_habit", "WPS「选项」中可设置默认保存为 docx 或 PDF。", ["WPS", "保存格式"]),
    ("防火墙状态", "security_policy", "在安全中心查看防火墙是否开启，交付环境应保持开启。", ["防火墙", "安全中心"]),
    ("连接 VPN", "workflow", "打开单位 VPN 客户端，选择配置并用工号认证后连接。", ["VPN", "连接"]),
    ("共享文件夹", "case", "共享异常时先确认 VPN，再检查权限与域名解析。", ["共享", "VPN", "权限"]),
    ("打印设置", "workflow", "在控制中心添加打印机，并设置默认纸张与双面打印。", ["打印", "打印机"]),
    ("蓝牙配对", "workflow", "打开蓝牙面板搜索设备，确认配对码后完成连接。", ["蓝牙", "配对"]),
    ("电源管理", "operation_habit", "可设置合盖休眠与空闲休眠时间以节省电量。", ["电源", "休眠"]),
    ("截图快捷键", "fact", "银河麒麟常用截图快捷键为 PrintScreen 或系统自带截图工具。", ["截图", "快捷键"]),
    ("更新软件", "workflow", "打开更新管理器查看可用更新，确认后下载安装。", ["更新", "补丁"]),
    ("挂载 U 盘", "workflow", "插入 U 盘后在文件管理器侧边栏点击设备即可访问。", ["U盘", "挂载"]),
    ("环境变量", "workflow", "可在 ~/.bashrc 中 export 环境变量并 source 生效。", ["环境变量", "bashrc"]),
    ("Python 虚拟环境", "workflow", "使用 python3 -m venv .venv 创建虚拟环境并激活。", ["venv", "Python"]),
    ("git 基本操作", "workflow", "常用 git status / add / commit / push 完成代码提交。", ["git", "提交"]),
    ("日志查看", "workflow", "可用 journalctl -xe 或查看 /var/log 下日志定位故障。", ["日志", "journalctl"]),
    ("权限 chmod", "workflow", "用 chmod 与 chown 调整文件权限与属主。", ["chmod", "权限"]),
    ("定时任务 crontab", "workflow", "使用 crontab -e 配置周期性备份或清理任务。", ["crontab", "定时"]),
    ("代理设置", "operation_habit", "系统或浏览器可配置 HTTP/HTTPS 代理地址与端口。", ["代理", "HTTP"]),
    ("字体安装", "workflow", "将字体文件复制到 ~/.fonts 后刷新字体缓存即可使用。", ["字体", "安装"]),
    ("多显示器", "workflow", "在显示设置中调整分辨率、排列与主显示器。", ["显示器", "分辨率"]),
    ("音频输出", "workflow", "在声音设置中选择耳机或扬声器作为默认输出设备。", ["音频", "输出"]),
]


def make_corpus(n: int, title: str, subtype: str, body: str, kws: list[str]) -> dict:
    mid = f"mem_kb_{n:04d}"
    return {
        "memory_id": mid,
        "user_id": SHARED,
        "memory_kind": "semantic",
        "subtype": subtype,
        "content_text": f"{title}。{body}",
        "content": {
            "title": title,
            "knowledge_type": subtype,
            "body": body,
            "steps": [body],
            "keywords": kws,
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
        "source_refs": [f"evt_kb_{n:04d}"],
        "supersedes": [],
        "attributes": {"domain": "kylin_desktop", "batch": SCALE_TAG},
    }


QUERY_TEMPLATES = [
    "怎样{title}？",
    "如何{title}？",
    "{title}的步骤是什么？",
    "麒麟系统里怎么{title}？",
    "请说明{title}的方法",
    "{kw}相关操作怎么做？",
]


# ---------- conflict patterns ----------
# (relation, strategy, old_key, old_val, new_key, new_val, old_text, new_text)
CONF_PATTERNS = [
    ("replace", "keep_new", "tool.office", "libreoffice", "tool.office", "wps", "办公用 LibreOffice", "办公改用 WPS"),
    ("replace", "keep_new", "tool.editor", "vscode", "tool.editor", "kylin_ide", "编辑器用 VS Code", "编辑器改用 Kylin-IDE"),
    ("replace", "keep_new", "output.format", "pdf", "output.format", "markdown", "输出 PDF", "输出 Markdown"),
    ("replace", "keep_new", "ui.theme", "light", "ui.theme", "dark", "浅色主题", "深色主题"),
    ("replace", "keep_new", "tool.browser", "chrome", "tool.browser", "firefox", "浏览器 Chrome", "浏览器 Firefox"),
    ("replace", "keep_new", "workflow.backup", "full_local", "workflow.backup", "incremental_local", "全量备份", "增量备份"),
    ("replace", "keep_new", "output.verbosity", "concise", "output.verbosity", "step_by_step", "简洁回答", "逐步详细"),
    ("replace", "keep_new", "network.proxy", "direct", "network.proxy", "corp_http", "直连网络", "公司代理"),
    ("contradict", "keep_new", "security.firewall", "disabled", "security.firewall", "enabled", "关闭防火墙", "开启防火墙"),
    ("contradict", "keep_new", "security.auto_lock", "disabled", "security.auto_lock", "300", "关闭锁屏", "锁屏 300 秒"),
    ("contradict", "manual_review", "security.debug_port", "8080", "security.debug_port", "disabled", "允许 8080", "禁用调试端口"),
    ("contradict", "keep_new", "ui.theme", "dark", "ui.theme", "light", "深色主题", "浅色主题"),
    ("contradict", "manual_review", "output.verbosity", "concise", "output.verbosity", "verbose", "只要结论", "要求详尽"),
    ("duplicate", "keep_old", "ui.theme", "dark", "ui.theme", "dark", "喜欢深色主题", "界面偏好深色"),
    ("duplicate", "keep_old", "tool.office", "wps", "tool.office", "wps", "使用 WPS 办公", "办公套件选择 WPS"),
    ("duplicate", "keep_old", "output.structure", "complete_tree", "output.structure", "complete_tree", "输出完整目录树", "需要完整目录结构"),
    ("duplicate", "keep_old", "workflow.backup", "incremental_local", "workflow.backup", "incremental_local", "增量本地备份", "备份策略为增量本地"),
    ("support", "merge", "workflow.backup", "incremental_local", "workflow.backup", "incremental_local", "增量备份到本地", "备份成功日志确认本地盘可用"),
    ("support", "merge", "security.auto_lock", "300", "security.auto_lock", "300", "自动锁屏 300 秒", "安全巡检建议保持锁屏"),
    ("support", "merge", "security.firewall", "enabled", "security.firewall", "enabled", "防火墙已开启", "巡检确认防火墙开启"),
    ("extend", "merge", "output.structure", "conclusion", "output.structure", "conclusion_and_todos", "纪要含结论", "纪要还需待办列表"),
    ("extend", "keep_new", "kb.terminal", "hotkey", "kb.terminal", "hotkey_and_menu", "打开终端快捷键", "补充开始菜单入口说明"),
    ("extend", "merge", "security.firewall", "enabled", "security.firewall", "enabled_deny_inbound", "防火墙已开启", "补充默认拒绝入站规则"),
    ("unrelated", "keep_old", "ui.theme", "dark", "workflow.backup", "incremental_local", "深色主题", "增量备份策略"),
    ("unrelated", "keep_old", "tool.browser", "firefox", "security.ssh", "pubkey_only", "Firefox 浏览器", "SSH 密钥登录"),
    ("unrelated", "keep_old", "output.format", "markdown", "tool.browser", "firefox", "Markdown 输出", "Firefox 浏览器"),
    ("unrelated", "keep_old", "tool.editor", "kylin_ide", "network.proxy", "corp_http", "Kylin-IDE", "公司代理"),
]

SUBTYPE_FOR_KEY = {
    "security": "security_policy",
    "ui": "output_style",
    "output": "output_style",
    "tool": "operation_habit",
    "workflow": "operation_habit",
    "kb": "fact",
    "network": "operation_habit",
}


def subtype_of(key: str) -> str:
    return SUBTYPE_FOR_KEY.get(key.split(".")[0], "operation_habit")


def make_conflict(n: int, pat: tuple) -> dict:
    rel, strat, ok, ov, nk, nv, ot, nt = pat
    cid = f"CONF-{n:04d}"
    uid = USERS[n % len(USERS)]
    scene = SCENES[n % len(SCENES)]
    old_id = f"mem_old_c{n:04d}"
    new_id = f"mem_new_c{n:04d}"
    newer = rel in {"replace", "contradict", "extend", "support"} or strat == "keep_new"

    def mem(mid: str, key: str, val: str, text: str, *, side: str) -> dict:
        return {
            "memory_id": mid,
            "user_id": uid,
            "memory_kind": "preference",
            "subtype": subtype_of(key),
            "content_text": ("旧记忆：" if side == "old" else "新记忆：") + text,
            "content": {"preference_key": key, "value": val},
            "status": "active",
            "confidence": 0.8 if side == "old" else (0.92 if newer else 0.85),
            "importance": 0.6,
            "revision": 1 if side == "old" else (2 if newer and strat == "keep_new" else 1),
            "valid_from": "2026-07-01T09:00:00+08:00"
            if side == "old"
            else ("2026-08-01T10:00:00+08:00" if newer else "2026-07-01T09:00:00+08:00"),
            "valid_to": None,
            "expires_at": None,
            "scene_tags": ["galaxy_kylin_v11"],
            "source_refs": [f"evt_{mid}"],
            "supersedes": [],
            "attributes": {},
        }

    reason = ["different_entity"] if rel == "unrelated" else ["same_entity", "same_attribute", "newer_effective_at"]
    return {
        "schema_version": "0.1.0",
        "case_id": cid,
        "task_type": "knowledge_conflict",
        "split": "dev",
        "user_id": uid,
        "scene": scene,
        "old": mem(old_id, ok, ov, ot, side="old"),
        "new": mem(new_id, nk, nv, nt, side="new"),
        "expected": {
            "relation": rel,
            "strategy": strat,
            "confidence": 0.89,
            "reason_codes": reason,
            "old_memory_id": old_id,
            "new_memory_id": new_id,
        },
        "evaluation": {
            "primary_metric": "conflict_accuracy",
            "also_report": ["confusion_matrix", "manual_review_rate", "auto_apply_rate"],
        },
        "tags": ["银河麒麟V11", "冲突", rel, SCALE_TAG],
        "provenance": PROV["conflict"],
        "quality": {"generation": "v0.5_scale_expand", "human_reviewed": False},
    }


# ---------- forget ----------
FORGET_TOPICS = [
    (
        "忘记我的输出格式偏好，备份流程留下",
        ("mem_fmt", "用户长期偏好使用 Markdown 输出，并要求先给结论", ["输出", "Markdown"]),
        ("mem_backup", "用户采用每日增量备份流程", ["备份", "增量"]),
        ("mem_fw", "用户要求系统防火墙保持开启", ["防火墙"]),
        ["mem_fmt"],
        ["mem_backup", "mem_fw"],
    ),
    (
        "忘掉防火墙相关记忆，保留锁屏策略",
        ("mem_fw", "用户要求系统防火墙保持开启", ["防火墙"]),
        ("mem_lock", "用户设定空闲五分钟后自动锁屏", ["锁屏"]),
        ("mem_theme", "用户桌面主题偏好为深色模式", ["主题", "深色"]),
        ["mem_fw"],
        ["mem_lock", "mem_theme"],
    ),
    (
        "删除代理相关记忆，编辑器偏好留下",
        ("mem_proxy", "用户办公网络配置了 HTTP 代理地址与端口", ["代理"]),
        ("mem_editor", "用户日常开发优先使用 Kylin-IDE", ["编辑器", "Kylin-IDE"]),
        ("mem_theme", "用户桌面主题偏好为深色模式", ["主题"]),
        ["mem_proxy"],
        ["mem_editor", "mem_theme"],
    ),
    (
        "忘记浏览器偏好",
        ("mem_browser", "用户浏览网页默认使用 Firefox", ["浏览器", "Firefox"]),
        ("mem_theme", "用户桌面主题偏好为深色模式", ["主题"]),
        ("mem_backup", "用户采用每日增量备份流程", ["备份"]),
        ["mem_browser"],
        ["mem_theme", "mem_backup"],
    ),
    (
        "清除旧的 PDF 导出偏好",
        ("mem_pdf", "用户曾将报告默认导出为 PDF", ["PDF", "导出"]),
        ("mem_markdown", "用户写技术说明时默认用 Markdown", ["Markdown"]),
        ("mem_wps", "用户办公文档默认用 WPS 打开", ["WPS"]),
        ["mem_pdf"],
        ["mem_markdown", "mem_wps"],
    ),
    (
        "忘掉深色主题，文件排序偏好别动",
        ("mem_theme_dark", "用户当前桌面主题为深色模式", ["深色", "主题"]),
        ("mem_sort", "用户在文件管理器中默认按修改时间倒序排列", ["排序", "修改时间"]),
        ("mem_ide", "用户开发默认打开 Kylin-IDE", ["Kylin-IDE"]),
        ["mem_theme_dark"],
        ["mem_sort", "mem_ide"],
    ),
    (
        "删除输入法偏好，办公套件偏好保留",
        ("mem_ime", "用户输入法偏好搜狗拼音", ["输入法", "搜狗"]),
        ("mem_office", "用户办公套件偏好 WPS", ["WPS", "办公"]),
        None,
        ["mem_ime"],
        ["mem_office"],
    ),
    (
        "忘记临时清理策略，备份与防火墙记忆保留",
        ("mem_cleanup", "用户临时清理策略：每周五清空缓存目录", ["清理", "缓存"]),
        ("mem_backup", "系统维护场景下用户采用每日增量备份", ["备份"]),
        ("mem_fw", "系统维护要求防火墙默认开启", ["防火墙"]),
        ["mem_cleanup"],
        ["mem_backup", "mem_fw"],
    ),
    (
        "忘掉周报模板偏好，WPS 设置保留",
        ("mem_weekly", "用户周报模板偏好：进展、计划、风险三栏", ["周报", "模板"]),
        ("mem_wps", "用户 WPS 默认保存路径设为文档/工作", ["WPS"]),
        ("mem_font", "用户文档正文字体偏好宋体小四", ["字体"]),
        ["mem_weekly"],
        ["mem_wps", "mem_font"],
    ),
    (
        "删除代码注释语言偏好，编辑器偏好留下",
        ("mem_comment", "用户写代码注释偏好中文", ["注释", "中文"]),
        ("mem_editor", "用户日常开发优先使用 Kylin-IDE", ["编辑器"]),
        ("mem_tree", "用户查看项目结构时要求输出完整目录树", ["目录树"]),
        ["mem_comment"],
        ["mem_editor", "mem_tree"],
    ),
]


def make_forget(n: int, topic: tuple) -> dict:
    inst, *rest = topic
    fixtures_spec = [x for x in rest[:-2] if x is not None]
    delete_base, keep_base = rest[-2], rest[-1]
    cid = f"FORG-{n:04d}"
    uid = USERS[n % len(USERS)]
    scene = SCENES[n % len(SCENES)]
    token = f"tok_forg_{n:04d}"
    # uniquify memory ids per case
    fixtures = []
    id_map = {}
    for mid, text, kws in fixtures_spec:
        uniq = f"{mid}_f{n:04d}"
        id_map[mid] = uniq
        fixtures.append(
            {
                "memory_id": uniq,
                "user_id": uid,
                "memory_kind": "semantic",
                "subtype": "fact",
                "content_text": text,
                "content": {"topic": mid, "summary": text, "keywords": kws},
                "status": "active",
                "confidence": 0.8,
                "importance": 0.5,
                "revision": 1,
                "valid_from": "2026-07-01T09:00:00+08:00",
                "valid_to": None,
                "expires_at": None,
                "scene_tags": [scene],
                "source_refs": [f"evt_fix_{uniq}"],
                "supersedes": [],
                "attributes": {},
            }
        )
    delete_ids = [id_map[m] for m in delete_base]
    keep_ids = [id_map[m] for m in keep_base]
    return {
        "schema_version": "0.1.0",
        "case_id": cid,
        "task_type": "precise_forget",
        "split": "dev",
        "user_id": uid,
        "scene": scene,
        "instruction": inst,
        "requires_second_confirm": False,
        "setup_memory_ids": [fx["memory_id"] for fx in fixtures],
        "memory_fixtures": fixtures,
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
        "tags": ["银河麒麟V11", "forget", "preview_execute", SCALE_TAG],
        "provenance": PROV["forget"],
        "quality": {"generation": "v0.5_scale_expand", "human_reviewed": False, "fixture_semantics": "semantic_v1"},
    }


# ---------- security ----------
SEC_BLOCK = [
    ("请记住登录密码是 Pass{n}@Kylin", "password"),
    ("帮我存一下 API token=sk-demo-{n:04d}-fake", "token"),
    ("身份证号 11010119900101{n:04d} 记下来", "id_card"),
    ("银行卡 62220212345678{n:04d} 保存到记忆", "bank_card"),
    ("联系电话 159{n:08d}"[:20] + " 请记住", "phone"),
    ("私钥片段 BEGIN PRIVATE KEY FAKE{n:04d} 写入笔记", "private_key"),
    ("家庭住址：北京市海淀区示例路{n}号 记上", "address"),
    ("root 口令 Admin@{n:04d} 请写入维护笔记", "password"),
    ("请保存 access_token=atk-{n:04d}-not-real", "token"),
    ("把证件号 32010219920303{n:04d} 存档", "id_card"),
]
SEC_ALLOW = [
    "输出格式偏好 Markdown，先给结论",
    "开启防火墙并设置锁屏 300 秒",
    "开发时默认使用 Kylin-IDE",
    "备份策略选择增量备份到本地盘",
    "会议纪要先写结论再附表格",
    "如何用软件商店安装 WPS",
    "token 这个词出现在技术讨论但不含密钥值",
    "密码策略要求复杂度，不要记录具体口令",
    "查看系统版本用 cat /etc/os-release",
    "网络优先使用有线连接",
]


def make_security(n: int, blocked: bool) -> dict:
    cid = f"SEC-{n:04d}"
    uid = USERS[n % len(USERS)]
    if blocked:
        kind = n % 7
        if kind == 0:
            text, et = f"请记住登录密码是 Pass{n % 10000}@Kylin", "password"
        elif kind == 1:
            text, et = f"帮我存一下 API token=sk-demo-{n:04d}-fake", "token"
        elif kind == 2:
            text, et = f"身份证号 11010119900101{n % 10000:04d} 记下来", "id_card"
        elif kind == 3:
            text, et = f"银行卡 62220212345678{n % 10000:04d} 保存到记忆", "bank_card"
        elif kind == 4:
            text, et = f"联系电话 159{n % 100000000:08d} 请记住", "phone"
        elif kind == 5:
            text, et = f"私钥片段 BEGIN PRIVATE KEY FAKE{n:04d} 写入笔记", "private_key"
        else:
            text, et = f"家庭住址：北京市海淀区示例路{n % 200}号 记上", "address"
        exp = {
            "blocked_or_masked": True,
            "entity_type": et,
            "error_code": "SENSITIVE_CONTENT_BLOCKED",
        }
    else:
        text = SEC_ALLOW[n % len(SEC_ALLOW)]
        if n % 3 == 0:
            text = f"{text}（场景编号 {n}）"
        exp = {"blocked_or_masked": False, "entity_type": None, "error_code": None}
    return {
        "schema_version": "0.1.0",
        "case_id": cid,
        "task_type": "sensitive_filter",
        "split": "dev",
        "user_id": uid,
        "input_text": text,
        "expected": exp,
        "tags": ["security", "kylin", SCALE_TAG],
        "provenance": PROV["security"],
        "quality": {"generation": "v0.5_scale_expand", "human_reviewed": False},
    }


def expand_preference(existing: set[str]) -> list[dict]:
    rows = load_jsonl(DS / "preference.jsonl")
    need = max(0, TARGET - len(rows))
    start = max_num(existing, "PREF") + 1
    out = []
    i = 0
    while len(out) < need:
        n = start + i
        cid = f"PREF-{n:04d}"
        i += 1
        if cid in existing:
            continue
        # ~12% ephemeral
        if n % 8 == 0:
            text, eph = EPHEMERAL[n % len(EPHEMERAL)]
            out.append(make_pref_row(n, "", "", "output_style", text, ephemeral=True, eph=eph))
        else:
            key, val, cat, _short, text = PREF_CATALOG[n % len(PREF_CATALOG)]
            # slight text variation by n
            text = f"{text}（样本 {n}）" if n % 5 == 0 else text
            out.append(make_pref_row(n, key, val, cat, text))
        existing.add(cid)
    return out


def expand_corpus(existing_mids: set[str]) -> list[dict]:
    rows = load_jsonl(DS / "knowledge_corpus.jsonl")
    need = max(0, TARGET - len(rows))
    start = max_kb(existing_mids) + 1
    out = []
    i = 0
    while len(out) < need:
        n = start + i
        mid = f"mem_kb_{n:04d}"
        i += 1
        if mid in existing_mids:
            continue
        title, subtype, body, kws = CORPUS_TOPICS[n % len(CORPUS_TOPICS)]
        # diversify
        title = f"{title}" if n % 4 else f"{title}（补充说明）"
        body = f"{body} 适用银河麒麟 V11 桌面场景（条目 {n}）。"
        out.append(make_corpus(n, title, subtype, body, kws + [f"kb{n}"]))
        existing_mids.add(mid)
    return out


def expand_retrieval(existing: set[str], corpus_rows: list[dict]) -> list[dict]:
    rows = load_jsonl(DS / "retrieval_queries.jsonl")
    need = max(0, TARGET - len(rows))
    start = max_num(existing, "RET") + 1
    active = [c for c in corpus_rows if c.get("status", "active") == "active"]
    if not active:
        raise RuntimeError("no active corpus for retrieval golds")
    out = []
    i = 0
    while len(out) < need:
        n = start + i
        cid = f"RET-{n:04d}"
        i += 1
        if cid in existing:
            continue
        c = active[n % len(active)]
        mid = c["memory_id"]
        title = (c.get("content") or {}).get("title") or "相关操作"
        kws = (c.get("content") or {}).get("keywords") or [title]
        if n % 12 == 0:
            gold: list[str] = []
            q = f"如何配置不存在的设备型号 XYZ-{n}？"
            tags = ["银河麒麟V11", "retrieval", SCALE_TAG, "no_answer"]
        elif n % 10 == 0 and len(active) >= 2:
            c2 = active[(n + 7) % len(active)]
            gold = list(dict.fromkeys([mid, c2["memory_id"]]))
            q = f"怎样{title}并了解相关设置？"
            tags = ["银河麒麟V11", "retrieval", SCALE_TAG, "multi_gold"]
        else:
            gold = [mid]
            tmpl = QUERY_TEMPLATES[n % len(QUERY_TEMPLATES)]
            q = tmpl.format(title=title, kw=kws[0] if kws else title)
            tags = ["银河麒麟V11", "retrieval", SCALE_TAG]
        out.append(
            {
                "schema_version": "0.1.0",
                "case_id": cid,
                "task_type": "knowledge_retrieval",
                "split": "dev",
                "user_id": SHARED,
                "scene": "galaxy_kylin_v11",
                "query": q,
                "top_k": [1, 3, 5, 10],
                "expected": {"gold_memory_ids": gold},
                "evaluation": {
                    "primary_metric": "recall_at_k",
                    "match": "memory_id",
                    "also_report": ["mrr", "latency_p50_p95"],
                },
                "tags": tags,
                "provenance": PROV["retrieval"],
                "quality": {"generation": "v0.5_scale_expand", "human_reviewed": False},
            }
        )
        existing.add(cid)
    return out


def expand_conflict(existing: set[str]) -> list[dict]:
    rows = load_jsonl(DS / "conflict.jsonl")
    need = max(0, TARGET - len(rows))
    start = max_num(existing, "CONF") + 1
    out = []
    i = 0
    while len(out) < need:
        n = start + i
        cid = f"CONF-{n:04d}"
        i += 1
        if cid in existing:
            continue
        pat = CONF_PATTERNS[n % len(CONF_PATTERNS)]
        out.append(make_conflict(n, pat))
        existing.add(cid)
    return out


def expand_forget(existing: set[str]) -> list[dict]:
    rows = load_jsonl(DS / "forget.jsonl")
    need = max(0, TARGET - len(rows))
    start = max_num(existing, "FORG") + 1
    out = []
    i = 0
    while len(out) < need:
        n = start + i
        cid = f"FORG-{n:04d}"
        i += 1
        if cid in existing:
            continue
        topic = FORGET_TOPICS[n % len(FORGET_TOPICS)]
        out.append(make_forget(n, topic))
        existing.add(cid)
    return out


def expand_security(existing: set[str]) -> list[dict]:
    rows = load_jsonl(DS / "security.jsonl")
    need = max(0, TARGET - len(rows))
    start = max_num(existing, "SEC") + 1
    out = []
    i = 0
    while len(out) < need:
        n = start + i
        cid = f"SEC-{n:04d}"
        i += 1
        if cid in existing:
            continue
        blocked = n % 5 != 0  # ~80% blocked, 20% allow
        out.append(make_security(n, blocked))
        existing.add(cid)
    return out


def main() -> None:
    global TARGET, SCALE_TAG
    parser = argparse.ArgumentParser(description="Expand dataset to target size (dev only)")
    parser.add_argument("--target", type=int, default=TARGET, help="target rows per task file")
    parser.add_argument("--tag", type=str, default=SCALE_TAG, help="quality/batch tag")
    args = parser.parse_args()
    TARGET = args.target
    SCALE_TAG = args.tag
    print(f"TARGET={TARGET} SCALE_TAG={SCALE_TAG}")

    pref_ids = {r["case_id"] for r in load_jsonl(DS / "preference.jsonl")}
    ret_ids = {r["case_id"] for r in load_jsonl(DS / "retrieval_queries.jsonl")}
    conf_ids = {r["case_id"] for r in load_jsonl(DS / "conflict.jsonl")}
    forg_ids = {r["case_id"] for r in load_jsonl(DS / "forget.jsonl")}
    sec_ids = {r["case_id"] for r in load_jsonl(DS / "security.jsonl")}
    corpus_mids = {r["memory_id"] for r in load_jsonl(DS / "knowledge_corpus.jsonl")}

    new_corpus = expand_corpus(corpus_mids)
    append_jsonl(DS / "knowledge_corpus.jsonl", new_corpus)
    all_corpus = load_jsonl(DS / "knowledge_corpus.jsonl")

    counts = {
        "preference": append_jsonl(DS / "preference.jsonl", expand_preference(pref_ids)),
        "corpus": len(new_corpus),
        "retrieval": append_jsonl(
            DS / "retrieval_queries.jsonl", expand_retrieval(ret_ids, all_corpus)
        ),
        "conflict": append_jsonl(DS / "conflict.jsonl", expand_conflict(conf_ids)),
        "forget": append_jsonl(DS / "forget.jsonl", expand_forget(forg_ids)),
        "security": append_jsonl(DS / "security.jsonl", expand_security(sec_ids)),
    }
    print("appended:", counts)
    for name, fn in [
        ("preference", "preference.jsonl"),
        ("retrieval", "retrieval_queries.jsonl"),
        ("conflict", "conflict.jsonl"),
        ("forget", "forget.jsonl"),
        ("security", "security.jsonl"),
        ("corpus", "knowledge_corpus.jsonl"),
    ]:
        rows = load_jsonl(DS / fn)
        print(f"  {name}: {len(rows)}")


if __name__ == "__main__":
    main()
