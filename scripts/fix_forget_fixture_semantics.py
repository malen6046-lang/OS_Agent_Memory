# -*- coding: utf-8 -*-
"""Fill forget.jsonl dev fixtures with real searchable semantics.

Only updates split=dev. validation / final_test remain frozen.
Does not put delete/keep answers into content_text.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORGET = ROOT / "evaluation" / "dataset" / "forget.jsonl"

# memory_id -> (content_text, content dict)
# Texts must be semantically matchable from natural-language forget instructions.
SEMANTICS: dict[str, tuple[str, dict]] = {
    # --- core / early cases ---
    "mem_fmt": (
        "用户长期偏好使用 Markdown 输出，并要求先给结论再展开细节",
        {
            "topic": "output_format",
            "summary": "Markdown 输出且先结论",
            "keywords": ["输出格式", "Markdown", "结论优先"],
        },
    ),
    "mem_backup": (
        "用户采用每日增量备份流程，备份目标为本地外置磁盘",
        {
            "topic": "backup_workflow",
            "summary": "每日增量本地备份",
            "keywords": ["备份", "增量", "每日"],
        },
    ),
    "mem_fw": (
        "用户要求系统防火墙保持开启，不允许为调试临时关闭",
        {
            "topic": "firewall_policy",
            "summary": "防火墙保持开启",
            "keywords": ["防火墙", "安全基线", "开启"],
        },
    ),
    "mem_lock": (
        "用户设定空闲五分钟后自动锁屏，锁屏需密码唤醒",
        {
            "topic": "screen_lock",
            "summary": "五分钟自动锁屏",
            "keywords": ["锁屏", "自动锁屏", "安全"],
        },
    ),
    "mem_theme": (
        "用户桌面主题偏好为深色模式，夜间办公时使用",
        {
            "topic": "ui_theme",
            "summary": "深色主题",
            "keywords": ["主题", "深色", "桌面"],
        },
    ),
    "mem_proxy": (
        "用户办公网络配置了 HTTP 代理地址与端口用于访问外网",
        {
            "topic": "http_proxy",
            "summary": "公司 HTTP 代理配置",
            "keywords": ["代理", "HTTP", "网络"],
        },
    ),
    "mem_token": (
        "用户曾保存过用于接口调试的访问令牌字符串备忘",
        {
            "topic": "access_token_note",
            "summary": "接口访问令牌备忘",
            "keywords": ["token", "令牌", "接口"],
        },
    ),
    "mem_editor": (
        "用户日常开发优先使用 Kylin-IDE，并习惯打开侧边文件树",
        {
            "topic": "editor_preference",
            "summary": "Kylin-IDE 为默认编辑器",
            "keywords": ["编辑器", "Kylin-IDE", "开发"],
        },
    ),
    "mem_project_x": (
        "星河专项会议纪要：下周交付演示环境，责任人为张工，会议室在三号楼",
        {
            "topic": "xinghe_project_meeting",
            "summary": "星河专项会议细节",
            "keywords": ["星河", "专项会议", "交付", "会议室"],
        },
    ),
    "mem_minutes_style": (
        "用户写会议纪要时习惯用三段结构：决议、待办、风险，并加粗决议标题",
        {
            "topic": "minutes_layout",
            "summary": "纪要排版三段结构",
            "keywords": ["纪要", "排版", "决议", "待办"],
        },
    ),
    "mem_wps": (
        "用户办公文档默认用 WPS 打开，保存格式优先 docx",
        {
            "topic": "office_suite",
            "summary": "默认使用 WPS",
            "keywords": ["WPS", "办公套件", "docx"],
        },
    ),
    "mem_temp_nolock": (
        "用户在演示当天临时关闭了自动锁屏，仅本次会议适用",
        {
            "topic": "temporary_nolock",
            "summary": "临时关闭自动锁屏例外",
            "keywords": ["临时", "关闭锁屏", "演示例外"],
        },
    ),
    "mem_proxy_personal": (
        "用户在个人场景使用本地 127.0.0.1 代理端口做抓包调试",
        {
            "topic": "proxy_personal",
            "summary": "个人场景本地代理",
            "keywords": ["个人场景", "代理", "抓包"],
        },
    ),
    "mem_proxy_delivery": (
        "交付现场场景统一走公司交付代理网关，禁止改用个人代理",
        {
            "topic": "proxy_delivery",
            "summary": "交付场景公司代理",
            "keywords": ["交付", "代理", "网关"],
        },
    ),
    "mem_browser": (
        "用户浏览网页默认使用 Firefox，并开启增强跟踪保护",
        {
            "topic": "browser_preference",
            "summary": "默认浏览器 Firefox",
            "keywords": ["浏览器", "Firefox", "偏好"],
        },
    ),
    "mem_secret_note": (
        "笔记中写有数据库密码明文：DbPass@2026，用于临时联调",
        {
            "topic": "password_note",
            "summary": "含密码字样的临时笔记",
            "keywords": ["密码", "明文", "笔记"],
        },
    ),
    "mem_vpn_guide": (
        "麒麟桌面连接单位 VPN 的标准步骤：打开 VPN 客户端、选择单位配置、输入工号认证",
        {
            "topic": "vpn_howto",
            "summary": "VPN 连接操作指南",
            "keywords": ["VPN", "连接", "排障"],
        },
    ),
    "mem_temp_en": (
        "本次客户演示要求输出全部使用英文，演示结束后不再沿用",
        {
            "topic": "temp_english_output",
            "summary": "演示用临时英文输出要求",
            "keywords": ["临时", "英文", "演示", "输出"],
        },
    ),
    "mem_zh_style": (
        "用户日常回复偏好简体中文，语气正式简洁",
        {
            "topic": "zh_output_style",
            "summary": "中文正式输出风格",
            "keywords": ["中文", "输出风格", "正式"],
        },
    ),
    "mem_dns_fix": (
        "共享文件夹无法访问时，曾采用修改 DNS 为 8.8.8.8 的临时修复方案",
        {
            "topic": "dns_fix",
            "summary": "DNS 修改修复方案",
            "keywords": ["DNS", "修复", "共享文件夹"],
        },
    ),
    "mem_vpn_fix": (
        "网络共享异常时优先检查 VPN 是否在线，再核对路由与域名解析",
        {
            "topic": "vpn_troubleshooting",
            "summary": "VPN 排障模板",
            "keywords": ["VPN", "排障", "模板"],
        },
    ),
    "mem_pdf": (
        "用户曾将报告默认导出为 PDF，并勾选嵌入字体选项",
        {
            "topic": "pdf_export",
            "summary": "旧 PDF 导出偏好",
            "keywords": ["PDF", "导出", "报告"],
        },
    ),
    "mem_markdown": (
        "用户写技术说明时默认用 Markdown，标题用二级标题开头",
        {
            "topic": "markdown_habit",
            "summary": "Markdown 写作习惯",
            "keywords": ["Markdown", "技术说明", "标题"],
        },
    ),
    "mem_debug_port": (
        "为本地调试曾放行 TCP 8080 端口，并在防火墙增加临时入站规则",
        {
            "topic": "debug_port_allow",
            "summary": "调试端口放行记录",
            "keywords": ["调试端口", "8080", "防火墙放行"],
        },
    ),
    "mem_theme_light": (
        "用户早期桌面主题为浅色模式，适合投影演示",
        {
            "topic": "theme_light",
            "summary": "浅色主题旧偏好",
            "keywords": ["浅色主题", "桌面", "投影"],
        },
    ),
    "mem_theme_dark": (
        "用户当前桌面主题为深色模式，并关闭夜间自动切换",
        {
            "topic": "theme_dark",
            "summary": "深色主题偏好",
            "keywords": ["深色主题", "桌面", "夜间"],
        },
    ),
    "mem_install_fail": (
        "软件商店安装驱动 XYZ 失败：依赖冲突，已记录错误码 0x4A，属短期排障记录",
        {
            "topic": "store_install_failure",
            "summary": "软件商店安装失败短期记录",
            "keywords": ["软件商店", "安装失败", "短期"],
        },
    ),
    "mem_install_ok": (
        "通过软件商店成功安装 WPS 的标准步骤：搜索、安装、授权本地文件关联",
        {
            "topic": "store_install_success",
            "summary": "商店安装成功流程",
            "keywords": ["软件商店", "安装成功", "WPS"],
        },
    ),
    # --- SCN-02 clone ---
    "mem_s02_project_x": (
        "星河专项办公会议：确认演示脚本与参会名单，地点在五号会议室",
        {
            "topic": "xinghe_office_meeting",
            "summary": "星河专项会议细节",
            "keywords": ["星河", "专项会议", "演示脚本"],
        },
    ),
    "mem_s02_minutes_style": (
        "办公助手纪要排版习惯：先写结论，再列行动项，最后附风险提示",
        {
            "topic": "office_minutes_style",
            "summary": "纪要排版习惯",
            "keywords": ["纪要", "排版", "行动项"],
        },
    ),
    "mem_s02_wps": (
        "办公助手用户默认用 WPS 处理会议纪要与通知附件",
        {
            "topic": "wps_office_habit",
            "summary": "WPS 办公习惯",
            "keywords": ["WPS", "会议纪要", "附件"],
        },
    ),
    # --- P3 hard / boundary (FORG-0022: fixtures must NOT mention bluetooth) ---
    "mem_h_fmt": (
        "用户长期偏好使用 Markdown 输出，并要求先给结论",
        {
            "topic": "output_format",
            "summary": "Markdown 输出且先结论",
            "keywords": ["输出格式", "Markdown", "结论"],
        },
    ),
    "mem_h_backup": (
        "用户采用每日增量备份流程",
        {
            "topic": "backup_workflow",
            "summary": "每日增量备份",
            "keywords": ["备份", "增量"],
        },
    ),
    "mem_h_fw": (
        "用户要求系统防火墙保持开启",
        {
            "topic": "firewall_policy",
            "summary": "防火墙保持开启",
            "keywords": ["防火墙", "开启"],
        },
    ),
    "mem_h2_secret": (
        "备忘录中记录了邮箱登录密码与二次验证码，仅限本人查看",
        {
            "topic": "password_memory",
            "summary": "密码相关记忆",
            "keywords": ["密码", "验证码", "邮箱"],
        },
    ),
    "mem_h2_theme": (
        "用户界面主题偏好深色，并降低动画强度",
        {
            "topic": "ui_theme",
            "summary": "深色界面主题",
            "keywords": ["主题", "深色", "界面"],
        },
    ),
    # --- v0.3 expand ---
    "mem_weekly_tpl": (
        "用户周报模板偏好：本周进展、下周计划、风险三栏，标题用日期命名",
        {
            "topic": "weekly_report_template",
            "summary": "周报模板偏好",
            "keywords": ["周报", "模板", "进展", "计划"],
        },
    ),
    "mem_wps_pref": (
        "用户 WPS 默认保存路径设为「文档/工作」，自动备份间隔 10 分钟",
        {
            "topic": "wps_settings",
            "summary": "WPS 保存与备份设置",
            "keywords": ["WPS", "保存路径", "自动备份"],
        },
    ),
    "mem_font": (
        "用户文档正文字体偏好宋体小四，英文用 Times New Roman",
        {
            "topic": "document_font",
            "summary": "文档字体偏好",
            "keywords": ["字体", "宋体", "Times New Roman"],
        },
    ),
    "mem_comment_lang": (
        "用户写代码注释偏好中文，公共 API 注释才用英文",
        {
            "topic": "code_comment_language",
            "summary": "代码注释语言偏好",
            "keywords": ["注释", "中文", "代码"],
        },
    ),
    "mem_tree": (
        "用户查看项目结构时要求输出完整目录树，并标注关键配置文件",
        {
            "topic": "directory_tree",
            "summary": "完整目录树输出习惯",
            "keywords": ["目录树", "项目结构", "配置文件"],
        },
    ),
    "mem_cleanup_tmp": (
        "用户临时清理策略：每周五清空 /tmp 与浏览器缓存，演示前可提前执行",
        {
            "topic": "temp_cleanup_policy",
            "summary": "临时清理策略",
            "keywords": ["临时清理", "/tmp", "缓存"],
        },
    ),
    "mem_backup_pol": (
        "系统维护场景下用户采用每日增量备份，并保留最近七天快照",
        {
            "topic": "backup_policy",
            "summary": "增量备份策略",
            "keywords": ["备份", "增量", "快照"],
        },
    ),
    "mem_fw_on": (
        "系统维护要求防火墙默认开启，变更前需二次确认",
        {
            "topic": "firewall_on",
            "summary": "防火墙开启策略",
            "keywords": ["防火墙", "开启", "二次确认"],
        },
    ),
    "mem_sort_mtime": (
        "用户在文件管理器中默认按修改时间倒序排列文件",
        {
            "topic": "file_sort_mtime",
            "summary": "按修改时间排序",
            "keywords": ["文件排序", "修改时间", "文件管理器"],
        },
    ),
    "mem_ide": (
        "用户开发默认打开 Kylin-IDE，并固定右侧终端面板",
        {
            "topic": "ide_preference",
            "summary": "Kylin-IDE 偏好",
            "keywords": ["Kylin-IDE", "编辑器", "终端面板"],
        },
    ),
    "mem_input_method": (
        "用户输入法偏好搜狗拼音，中英切换快捷键为 Ctrl+Shift",
        {
            "topic": "input_method",
            "summary": "输入法偏好",
            "keywords": ["输入法", "搜狗", "Ctrl+Shift"],
        },
    ),
    "mem_office_wps": (
        "用户办公套件偏好 WPS，表格默认使用 et 格式打开",
        {
            "topic": "office_wps",
            "summary": "办公套件 WPS 偏好",
            "keywords": ["办公套件", "WPS", "表格"],
        },
    ),
    "mem_proj_detail": (
        "某次客户会议专项细节：预算上限、演示账号与临时访问码已记在备忘中",
        {
            "topic": "meeting_project_detail",
            "summary": "会议专项细节",
            "keywords": ["会议", "专项", "预算", "演示账号"],
        },
    ),
}


FORBIDDEN_LEAK = ("应删除", "应保留", "should_delete", "should_keep", "标准答案")


def apply_fixture(fx: dict) -> None:
    mid = fx["memory_id"]
    if mid not in SEMANTICS:
        raise KeyError(f"missing semantics for {mid}")
    text, content = SEMANTICS[mid]
    for bad in FORBIDDEN_LEAK:
        if bad in text:
            raise ValueError(f"{mid} content_text leaks answer marker {bad!r}")
    fx["content_text"] = text
    fx["content"] = content


def main() -> None:
    rows: list[str] = []
    updated_cases = 0
    updated_fixtures = 0
    missing: set[str] = set()

    with FORGET.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            if o.get("split") == "dev":
                touched = False
                for fx in o.get("memory_fixtures") or []:
                    mid = fx.get("memory_id", "")
                    if mid not in SEMANTICS:
                        missing.add(mid)
                        continue
                    apply_fixture(fx)
                    updated_fixtures += 1
                    touched = True
                if touched:
                    updated_cases += 1
                    o.setdefault("quality", {})["fixture_semantics"] = "semantic_v1"
            rows.append(json.dumps(o, ensure_ascii=False))

    if missing:
        raise SystemExit(f"dev fixtures missing semantics: {sorted(missing)}")

    FORGET.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"updated_cases={updated_cases} updated_fixtures={updated_fixtures} -> {FORGET}")


if __name__ == "__main__":
    main()
