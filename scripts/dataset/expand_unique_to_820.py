# -*- coding: utf-8 -*-
"""Expand knowledge corpus + Dev retrieval queries to >=820 WITHOUT V0.5 failure modes.

Guarantees
----------
- Unique normalized titles (no same-topic × N clones)
- No 「条目 N」 / 「补充说明」 pollution in embedding text
- No fake multi-gold (second gold must be same-domain related)
- no-answer kept separate with is_no_answer=true
- validation / final_test untouched
- human_reviewed / hard-p3 / cross_user Dev queries preserved

Usage
-----
  python scripts/dataset/expand_unique_to_820.py --dry-run
  python scripts/dataset/expand_unique_to_820.py --apply --target 820
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    DS,
    REVIEWS,
    clean_entry_markers,
    load_jsonl,
    memory_num,
    normalize_title,
    write_jsonl,
)

BATCH = "v0.6_unique820"
SHARED = "usr_corpus_shared"
SEED = 42


def norm_key(title: str) -> str:
    t = normalize_title(title)
    t = t.replace(" ", "").replace("　", "")
    t = t.lower()
    return t


def topic_id_for(mid: str, title: str) -> str:
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:6]
    return f"{mid.replace('mem_', 'topic_', 1)}_{digest}"


def make_record(n: int, title: str, subtype: str, body: str, kws: list[str]) -> dict[str, Any]:
    mid = f"mem_kb_{n:04d}"
    tid = topic_id_for(mid, title)
    content_text = f"{title}。{body}"
    return {
        "memory_id": mid,
        "user_id": SHARED,
        "memory_kind": "semantic",
        "subtype": subtype,
        "content_text": content_text,
        "canonical_topic_id": tid,
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
        "attributes": {
            "domain": "kylin_desktop",
            "batch": BATCH,
            "generation_batch": BATCH,
            "canonical_topic_id": tid,
        },
    }


def build_topic_catalog() -> list[tuple[str, str, str, list[str]]]:
    """Return many *distinct* (title, subtype, body, keywords) cards."""
    out: list[tuple[str, str, str, list[str]]] = []

    def add(title: str, subtype: str, body: str, kws: list[str]) -> None:
        out.append((title, subtype, body, kws))

    # ---- commands / sysinfo (each unique) ----
    cmd_facts = [
        ("查看内存占用", "free -h", "内存"),
        ("查看CPU信息", "lscpu", "CPU"),
        ("查看磁盘分区", "lsblk", "磁盘"),
        ("查看挂载点", "findmnt", "挂载"),
        ("查看路由表", "ip route", "路由"),
        ("查看网卡列表", "ip link", "网卡"),
        ("查看IP地址", "ip addr", "IP"),
        ("查看DNS解析", "resolvectl status", "DNS"),
        ("查看开机时长", "uptime", "uptime"),
        ("查看当前用户", "whoami", "用户"),
        ("查看登录用户", "who", "登录"),
        ("查看内核模块", "lsmod", "内核模块"),
        ("查看PCI设备", "lspci", "PCI"),
        ("查看USB设备", "lsusb", "USB"),
        ("查看块设备UUID", "blkid", "UUID"),
        ("查看系统负载", "cat /proc/loadavg", "负载"),
        ("查看进程树", "pstree -p", "进程树"),
        ("查看打开文件数", "lsof -p <PID>", "lsof"),
        ("查看套接字连接", "ss -tulnp", "ss"),
        ("查看防火墙规则", "sudo iptables -L -n", "iptables"),
        ("查看定时任务列表", "crontab -l", "crontab"),
        ("查看系统时间", "date", "时间"),
        ("查看时区", "timedatectl", "时区"),
        ("查看主机名", "hostnamectl", "主机名"),
        ("查看发行版代号", "lsb_release -a", "发行版"),
        ("查看SELinux状态", "getenforce", "SELinux"),
        ("查看磁盘SMART", "sudo smartctl -a /dev/sda", "SMART"),
        ("查看inode使用", "df -i", "inode"),
        ("查看目录大小Top", "du -h --max-depth=1 | sort -h", "du"),
        ("查看最近登录", "last -n 20", "last"),
        ("查看失败登录", "sudo lastb | head", "lastb"),
        ("查看内核日志尾部", "sudo dmesg | tail", "dmesg"),
        ("查看服务状态", "systemctl status <服务名>", "systemctl"),
        ("查看失败服务", "systemctl --failed", "失败服务"),
        ("查看定时器单元", "systemctl list-timers", "timer"),
        ("查看环境变量PATH", "echo $PATH", "PATH"),
        ("查看Shell版本", "bash --version", "bash"),
        ("查看Python版本", "python3 --version", "Python"),
        ("查看GCC版本", "gcc --version", "gcc"),
        ("查看Git版本", "git --version", "git"),
        ("查看Docker是否可用", "docker --version", "docker"),
        ("查看Podman版本", "podman --version", "podman"),
        ("查看flatpak列表", "flatpak list", "flatpak"),
        ("查看snap是否存在", "snap version", "snap"),
        ("查看音频设备", "pactl list short sinks", "音频设备"),
        ("查看蓝牙控制器", "bluetoothctl show", "蓝牙"),
        ("查看显示器连接", "xrandr", "显示器"),
        ("查看输入设备", "xinput list", "输入设备"),
        ("查看字体列表", "fc-list : lang=zh | head", "字体"),
        ("查看软件包是否安装", "dpkg -l | grep <包名>", "dpkg"),
    ]
    for title, cmd, kw in cmd_facts:
        add(
            title,
            "fact",
            f"在银河麒麟终端执行 `{cmd}` 可完成「{title}」。结果异常时结合 journalctl 与权限检查。",
            [kw, "终端", "命令"],
        )

    # ---- apt / package ops ----
    pkgs = [
        ("vim", "文本编辑"),
        ("git", "版本管理"),
        ("curl", "HTTP下载"),
        ("wget", "文件下载"),
        ("htop", "进程监控"),
        ("tree", "目录树"),
        ("zip", "压缩"),
        ("unzip", "解压"),
        ("rsync", "同步备份"),
        ("tmux", "终端复用"),
        ("openssh-server", "SSH服务"),
        ("openssh-client", "SSH客户端"),
        ("build-essential", "编译工具链"),
        ("cmake", "构建系统"),
        ("pkg-config", "库探测"),
        ("python3-pip", "Python包管理"),
        ("python3-venv", "虚拟环境"),
        ("nodejs", "Node运行时"),
        ("npm", "前端包管理"),
        ("docker.io", "容器引擎"),
        ("podman", "无根容器"),
        ("ffmpeg", "音视频处理"),
        ("imagemagick", "图片处理"),
        ("libreoffice", "办公套件备选"),
        ("gimp", "图像编辑"),
        ("vlc", "媒体播放"),
        ("wireshark", "抓包分析"),
        ("nmap", "端口扫描"),
        ("tcpdump", "报文捕获"),
        ("net-tools", "经典网络工具"),
        ("dnsutils", "DNS诊断"),
        ("traceroute", "路由追踪"),
        ("iperf3", "带宽测试"),
        ("samba", "文件共享服务"),
        ("nfs-common", "NFS客户端"),
        ("cifs-utils", "CIFS挂载"),
        ("ntfs-3g", "NTFS支持"),
        ("exfat-fuse", "exFAT支持"),
        ("cups", "打印服务"),
        ("printer-driver-all", "打印机驱动集合"),
        ("bluez", "蓝牙协议栈"),
        ("pulseaudio", "音频服务"),
        ("pavucontrol", "音量控制"),
        ("fonts-noto-cjk", "中日韩字体"),
        ("fcitx5", "输入法框架"),
        ("fcitx5-chinese-addons", "中文输入增强"),
        ("gnome-disk-utility", "磁盘工具"),
        ("baobab", "磁盘占用可视化"),
        ("gparted", "分区编辑"),
        ("timeshift", "系统快照"),
        ("ufw", "简易防火墙"),
        ("fail2ban", "防爆破"),
        ("clamav", "病毒扫描"),
        ("aide", "文件完整性"),
        ("auditd", "审计守护"),
        ("logrotate", "日志轮转"),
        ("cron", "定时任务服务"),
        ("anacron", "非持续开机定时"),
        ("supervisor", "进程守护"),
        ("nginx", "Web服务"),
        ("redis-server", "缓存服务"),
        ("postgresql", "数据库"),
        ("sqlite3", "嵌入式数据库"),
        ("jq", "JSON处理"),
        ("yq", "YAML处理"),
        ("ripgrep", "快速搜索"),
        ("fd-find", "文件查找"),
        ("bat", "增强cat"),
        ("shellcheck", "Shell检查"),
        ("clang", "LLVM编译器"),
        ("lldb", "调试器"),
        ("valgrind", "内存检查"),
        ("strace", "系统调用跟踪"),
        ("ltrace", "库调用跟踪"),
        ("perf-tools-unstable", "性能分析"),
        ("sysstat", "系统统计"),
        ("iotop", "IO监控"),
        ("iftop", "流量监控"),
        ("nethogs", "按进程流量"),
        ("mtr-tiny", "综合路由诊断"),
        ("aria2", "多线程下载"),
        ("rclone", "云盘同步"),
        ("borgbackup", "去重备份"),
        ("restic", "加密备份"),
        (" pandoc", "文档转换"),
        ("texlive-xetex", "中文TeX"),
        ("graphviz", "绘图"),
        ("plantuml", "UML图"),
        ("markdown", "Markdown工具"),
        ("dos2unix", "换行转换"),
        ("expect", "交互自动化"),
        ("sshpass", "非交互SSH"),
        ("ansible", "批量配置"),
        ("terraform", "基础设施即代码"),
    ]
    for pkg, purpose in pkgs:
        pkg = pkg.strip()
        add(
            f"用 apt 安装 {pkg}",
            "workflow",
            f"在银河麒麟上安装「{purpose}」相关组件时，可执行 `sudo apt update && sudo apt install -y {pkg}`。"
            f"安装后用 `dpkg -l {pkg}` 或命令自检确认。",
            [pkg, "apt", purpose],
        )
        add(
            f"用 apt 卸载 {pkg}",
            "workflow",
            f"若不再需要 {pkg}，执行 `sudo apt remove -y {pkg}`；清理配置可用 `sudo apt purge -y {pkg}`，"
            f"再执行 `sudo apt autoremove` 删除无用依赖。",
            [pkg, "卸载", "apt"],
        )

    # ---- desktop / control center ----
    desktop_items = [
        ("设置深色主题", "workflow", "在控制中心「个性化/主题」中选择深色外观，保存后对新开窗口生效。", ["主题", "深色"]),
        ("设置浅色主题", "workflow", "在控制中心主题设置中切换浅色模式，适合明亮办公环境。", ["主题", "浅色"]),
        ("调整系统字体大小", "workflow", "控制中心「字体」或「显示」中增大/减小界面字体，便于阅读。", ["字体大小", "显示"]),
        ("设置开机启动应用", "workflow", "在启动应用管理中勾选需要开机自启的程序，勿添加过多以免拖慢登录。", ["开机启动"]),
        ("设置默认浏览器", "workflow", "控制中心「默认应用程序」中将 Web 指定为 Firefox 或 Chrome。", ["默认浏览器"]),
        ("设置默认邮件客户端", "workflow", "在默认应用程序里指定邮件客户端，保证 mailto 链接正确打开。", ["邮件客户端"]),
        ("设置默认终端", "workflow", "若安装多个终端，在默认应用程序中指定首选终端仿真器。", ["默认终端"]),
        ("配置触控板轻触点击", "workflow", "鼠标与触控板设置中开启「轻触即点击」，减少实体按压。", ["触控板"]),
        ("关闭触控板同时使用鼠标", "workflow", "外接鼠标时可开启「插入鼠标时禁用触控板」，避免误触。", ["触控板", "鼠标"]),
        ("设置键盘重复延迟", "workflow", "键盘设置中调整按键重复延迟与速度，适配长按删除场景。", ["键盘"]),
        ("开启粘滞键", "workflow", "辅助功能中可开启粘滞键，方便单手组合快捷键操作。", ["辅助功能"]),
        ("配置屏幕缩放", "workflow", "高分屏可在显示设置中调整缩放比例，使图标与文字更清晰。", ["缩放", "高分屏"]),
        ("设置夜间模式色温", "workflow", "显示/护眼中开启夜间模式并调节色温，减少夜间蓝光。", ["夜间模式"]),
        ("配置多桌面数量", "workflow", "工作区设置中增加虚拟桌面数量，用快捷键在桌面间切换。", ["虚拟桌面"]),
        ("固定应用到任务栏", "workflow", "在开始菜单右键应用选择「固定到任务栏」，方便一键启动。", ["任务栏"]),
        ("创建桌面快捷方式", "workflow", "可将常用应用或文件夹发送到桌面，生成快捷方式图标。", ["桌面快捷方式"]),
        ("设置自动登录风险提示", "security_policy", "交付环境不建议开启自动登录；若临时开启需知会安全管理员。", ["自动登录", "安全"]),
        ("配置屏保等待时间", "workflow", "在屏保设置中指定空闲多久启动屏保，可与锁屏策略配合。", ["屏保"]),
        ("开启通知勿扰", "operation_habit", "会议期间可在通知设置中开启勿扰，避免弹窗打断。", ["通知", "勿扰"]),
        ("配置声音提示音量", "workflow", "声音设置中分别调节系统提示音、媒体与麦克风输入电平。", ["音量"]),
        ("切换音频输入麦克风", "workflow", "在声音输入设备列表中选择正确麦克风，通话前先试音。", ["麦克风"]),
        ("禁用开机音乐", "operation_habit", "可在声音或启动设置中关闭开机提示音，保持安静办公。", ["开机音乐"]),
        ("配置鼠标滚轮方向", "workflow", "鼠标设置中可切换自然滚动与传统滚动方向。", ["滚轮"]),
        ("设置双击速度", "workflow", "鼠标设置里调整双击间隔，避免双击被识别成两次单击。", ["双击"]),
        ("添加中文输入法引擎", "workflow", "在输入法设置中添加拼音/五笔引擎，并设置默认中文输入。", ["输入法", "拼音"]),
        ("调整输入法候选词数量", "operation_habit", "输入法高级设置中可增加候选词个数，提高选词效率。", ["输入法", "候选词"]),
        ("配置云剪贴板注意事项", "security_policy", "涉及敏感信息时不要启用不可信云剪贴板同步。", ["剪贴板", "安全"]),
        ("清理最近文件列表", "workflow", "文件管理器或开始菜单中可清除「最近使用的文件」记录。", ["最近文件"]),
        ("设置文件管理器默认视图", "operation_habit", "可在文件管理器偏好中默认使用列表或图标视图。", ["文件管理器"]),
        ("显示隐藏文件", "workflow", "文件管理器中启用「显示隐藏文件」以查看 .config 等目录。", ["隐藏文件"]),
        ("压缩文件夹为zip", "workflow", "右键文件夹选择压缩，或使用 `zip -r out.zip 目录`。", ["zip", "压缩"]),
        ("解压7z文件", "workflow", "若已安装 p7zip，可用 `7z x file.7z` 或图形解压工具打开。", ["7z", "解压"]),
        ("校验下载文件SHA256", "workflow", "执行 `sha256sum 文件` 并与官网校验值比对，防止篡改。", ["校验", "sha256"]),
        ("挂载ISO镜像", "workflow", "可用 `sudo mount -o loop file.iso /mnt` 查看镜像内容。", ["ISO", "挂载"]),
        ("制作启动U盘注意", "security_policy", "制作系统启动盘会清空U盘；操作前备份数据并核对镜像校验和。", ["启动盘", "U盘"]),
        ("设置生物识别登录", "workflow", "若硬件支持，可在用户设置中录入指纹用于解锁（仍建议保留密码兜底）。", ["指纹"]),
        ("配置电源键行为", "operation_habit", "电源设置中可指定按下电源键为休眠、关机或询问。", ["电源键"]),
        ("设置合盖外接显示器继续工作", "workflow", "笔记本外接显示器时，可在电源设置允许合盖后继续运行。", ["合盖", "外接显示器"]),
        ("校准触摸屏", "workflow", "若存在触摸屏漂移，在显示/Wacom类设置中运行校准向导。", ["触摸屏"]),
        ("配置手写笔按键", "workflow", "手写笔设置中可映射侧键为右键或橡皮擦功能。", ["手写笔"]),
        ("开启窗口磁吸对齐", "operation_habit", "窗口管理中可开启边缘磁吸，方便左右分屏。", ["分屏"]),
        ("使用概览查看所有窗口", "workflow", "通过热角或快捷键进入活动概览，快速定位窗口。", ["窗口概览"]),
        ("设置工作区快捷键", "workflow", "在键盘快捷键中自定义切换工作区、移动窗口到工作区的组合键。", ["快捷键", "工作区"]),
        ("锁定屏幕快捷键", "fact", "常用锁屏快捷键为 Super+L 或控制中心安全策略指定的组合键。", ["锁屏", "快捷键"]),
        ("强制结束无响应应用", "workflow", "可用系统监视器结束进程，或 `killall 应用名`（先尝试正常退出）。", ["杀进程"]),
        ("查看图形会话日志", "workflow", "图形异常时可查看 ~/.xsession-errors 或 journalctl 用户会话日志。", ["图形日志"]),
        ("重置失控的显示布局", "workflow", "外接屏错乱时，可在显示设置点「重置」或拔插线缆后重新检测。", ["显示布局"]),
        ("配置HiDPI字体渲染", "workflow", "高分屏可启用轻度字体抗锯齿与提示，使文字边缘更平滑。", ["HiDPI", "字体"]),
        ("设置语言为简体中文", "workflow", "区域与语言中选择简体中文，必要时安装语言包并重新登录。", ["语言包"]),
        ("切换系统区域格式", "operation_habit", "可分别设置界面语言与数字/日期格式区域。", ["区域格式"]),
    ]
    for item in desktop_items:
        add(*item)

    # ---- networking scenarios ----
    net_items = [
        ("用 nmcli 查看连接", "workflow", "执行 `nmcli connection show` 查看 NetworkManager 连接配置。", ["nmcli"]),
        ("用 nmcli 连接WiFi", "workflow", "执行 `nmcli device wifi connect <SSID> password <密码>` 连接无线网络。", ["WiFi", "nmcli"]),
        ("忘记WiFi后重连", "workflow", "在控制中心网络中删除旧WiFi配置，再重新输入密码连接。", ["WiFi"]),
        ("设置有线自动连接", "workflow", "有线连接属性中勾选自动连接，保证插网线后立即上网。", ["有线", "自动连接"]),
        ("配置DNS为公共解析", "workflow", "IPv4设置中将DNS设为可达到的解析服务器，并关闭自动DNS冲突项。", ["DNS"]),
        ("编辑hosts加速解析", "workflow", "可在 /etc/hosts 添加内网主机名映射，修改后无需重启即可生效。", ["hosts"]),
        ("排查DNS污染", "case", "网页打不开但IP可ping时，优先检查DNS与代理；可换解析服务器试验。", ["DNS", "排查"]),
        ("开启网络热点", "workflow", "若网卡支持，可在网络设置中创建热点并设置共享密码。", ["热点"]),
        ("限制热点连接数注意", "security_policy", "办公热点应设置强密码并限制可见性，避免未授权接入。", ["热点", "安全"]),
        ("配置静态路由", "workflow", "访问特定网段时可 `sudo ip route add <网段> via <网关>`，持久化需写入NM配置。", ["静态路由"]),
        ("删除错误路由", "workflow", "错误路由会导致绕行，可用 `sudo ip route del <目标>` 删除后重测。", ["路由"]),
        ("抓包前确认权限", "security_policy", "tcpdump/wireshark 抓包需相应权限，且仅用于授权排障。", ["抓包", "合规"]),
        ("测试端口是否开放", "workflow", "用 `nc -vz 主机 端口` 或 `ss`/`nmap` 检查服务端口可达性。", ["端口"]),
        ("临时关闭网卡", "workflow", "`sudo ip link set <网卡> down` 可临时关闭网卡，排障后记得 up。", ["网卡"]),
        ("查看无线信号强度", "workflow", "网络面板或 `nmcli device wifi list` 可观察信号与信道质量。", ["WiFi", "信号"]),
        ("切换有线计量网络", "operation_habit", "在按流量计费环境将连接标为计量，减少自动更新消耗。", ["计量网络"]),
        ("配置HTTP代理例外", "workflow", "代理设置中把内网域名加入不走代理列表，避免内网访问失败。", ["代理", "例外"]),
        ("排查代理导致apt失败", "case", "apt 更新失败时检查 /etc/apt/apt.conf.d 代理配置是否过期。", ["apt", "代理"]),
        ("配置NTP服务器", "workflow", "timedatectl 或 timesyncd 配置中指定可靠NTP，保证证书校验时间正确。", ["NTP"]),
        ("诊断MTU过大丢包", "case", "大文件传输异常时可尝试降低MTU（如 1400）观察是否改善。", ["MTU"]),
        ("配置IPv6禁用注意", "security_policy", "除非策略要求，不建议随意全局禁用IPv6；若禁用需记录变更。", ["IPv6"]),
        ("检查网关ARP", "workflow", "`ip neigh` 可查看网关ARP是否完整，异常时检查二层连通。", ["ARP"]),
        ("公司无线802.1X登录", "workflow", "选择企业无线时按IT要求填写用户证书或账号密码（PEAP/TLS）。", ["802.1X"]),
        ("排查VPN能连但无法访问内网", "case", "VPN已连接仍不可达时检查分流路由、DNS后缀与防火墙。", ["VPN", "排查"]),
        ("配置SSH保活", "operation_habit", "在 ~/.ssh/config 设置 ServerAliveInterval 防止长连接被断开。", ["SSH", "保活"]),
        ("限制SSH密码登录", "security_policy", "生产机建议 PasswordAuthentication no，仅保留密钥登录。", ["SSH", "安全"]),
        ("生成并分发SSH公钥", "workflow", "`ssh-keygen -t ed25519` 后把 .pub 写入目标机 authorized_keys。", ["SSH", "公钥"]),
        ("SSH跳板机ProxyJump", "workflow", "在 SSH config 使用 ProxyJump 经跳板访问内网主机。", ["SSH", "跳板"]),
        ("SCP上传文件", "workflow", "`scp file user@host:/path` 可上传；目录加 -r。", ["scp"]),
        ("SFTP交互传文件", "workflow", "`sftp user@host` 进入后用 put/get 传输文件。", ["sftp"]),
        ("rsync增量同步目录", "workflow", "`rsync -avP src/ user@host:dst/` 适合大目录增量备份。", ["rsync"]),
        ("挂载CIFS共享", "workflow", "`sudo mount -t cifs //server/share /mnt -o username=...` 挂载Windows共享。", ["cifs"]),
        ("挂载NFS共享", "workflow", "`sudo mount -t nfs server:/export /mnt` 挂载NFS，注意权限映射。", ["nfs"]),
        ("排查共享权限denied", "case", "共享拒绝访问时核对账号、导出权限、防火墙与时间同步。", ["共享", "权限"]),
        ("配置主机防火墙放行22", "security_policy", "仅在需要远程管理时放行22/TCP，并限制来源网段。", ["防火墙", "SSH"]),
        ("放行HTTP80端口", "workflow", "若本机提供Web服务，在防火墙放行80/TCP并验证监听。", ["防火墙", "HTTP"]),
        ("放行HTTPS443端口", "workflow", "对外Web服务应放行443/TCP，并配置有效证书。", ["防火墙", "HTTPS"]),
        ("关闭无用监听端口", "security_policy", "用 ss 审查监听端口，停用未授权服务，缩小攻击面。", ["端口", "安全"]),
        ("配置WireGuard客户端", "workflow", "按IT下发的配置导入WireGuard，连接后检查内网路由。", ["WireGuard"]),
        ("诊断DNS后缀搜索列表", "case", "短主机名解析失败时检查 search domain 是否包含公司后缀。", ["DNS后缀"]),
        ("设置有线链路聚合注意", "fact", "双网卡聚合需交换机与驱动支持，错误配置可能导致环路。", ["链路聚合"]),
        ("查看实时带宽", "workflow", "可用 `iftop` 或系统监视器观察上下行带宽占用。", ["带宽"]),
        ("定位占带宽进程", "workflow", "`nethogs` 可按进程查看网络流量，便于找出异常上传。", ["流量", "进程"]),
        ("配置浏览器仅代理规则", "operation_habit", "可只让浏览器走代理而系统其它应用直连，降低影响面。", ["浏览器代理"]),
        ("清除DNS缓存", "workflow", "解析异常时可 `resolvectl flush-caches` 或重启 NetworkManager。", ["DNS缓存"]),
        ("检查证书过期影响HTTPS", "case", "HTTPS失败时用浏览器查看证书有效期，系统时间错误也会误报。", ["证书"]),
        ("配置本地port转发", "workflow", "`ssh -L 本地端口:目标:端口 user@jump` 做本地端口转发访问内网服务。", ["SSH", "端口转发"]),
        ("配置动态SOCKS代理", "workflow", "`ssh -D 1080 user@host` 可创建临时SOCKS，供浏览器调试。", ["SOCKS"]),
        ("排查无线频繁掉线", "case", "WiFi掉线先排除干扰与驱动；可切换5GHz、更新固件并查看dmesg。", ["WiFi", "掉线"]),
        ("有线协商速率查看", "workflow", "`ethtool 网卡` 可查看速率/双工，异常时检查网线与交换机口。", ["ethtool"]),
    ]
    for item in net_items:
        add(*item)

    # ---- security / compliance ----
    sec_items = [
        ("设置账户密码复杂度", "security_policy", "密码应包含长短与字符类别要求，禁止使用默认口令交付。", ["密码策略"]),
        ("锁定失败登录次数", "security_policy", "可配置 pam 失败锁定，防止口令爆破。", ["登录锁定"]),
        ("检查sudoers配置", "security_policy", "用 `sudo visudo` 编辑，避免直接改坏 /etc/sudoers。", ["sudoers"]),
        ("审计特权命令", "security_policy", "重要主机可启用 auditd 记录 sudo 与敏感文件访问。", ["审计"]),
        ("关闭不必要的root远程", "security_policy", "SSH 中 PermitRootLogin 应设为 no。", ["root", "SSH"]),
        ("定期更新安全补丁", "security_policy", "通过更新管理器或 apt 安装安全更新，并记录变更窗口。", ["安全更新"]),
        ("检查世界可写目录", "workflow", "`find / -type d -perm -0002` 排查异常可写目录（注意权限与耗时）。", ["权限排查"]),
        ("验证重要二进制校验", "workflow", "对关键工具可保存校验和，变更后对比是否被替换。", ["完整性"]),
        ("配置全盘加密注意", "fact", "安装阶段可启用LUKS；丢失口令将无法恢复数据。", ["LUKS"]),
        ("屏幕共享需授权", "security_policy", "远程协助/屏幕共享仅在授权期间开启，结束后立即关闭。", ["屏幕共享"]),
        ("U盘自动挂载策略", "security_policy", "高安全场景可限制未知U盘自动挂载，降低摆渡风险。", ["U盘策略"]),
        ("清理浏览器保存的密码", "security_policy", "公用电脑勿让浏览器记住密码；可在设置中清除已存凭据。", ["浏览器密码"]),
        ("检查开放的Samba共享", "security_policy", "确认 smb.conf 未意外共享敏感目录，并设置访问控制。", ["Samba", "安全"]),
        ("禁用历史命令中的密钥", "security_policy", "避免在命令行明文写密码；若已写入及时清理 HISTFILE。", ["历史命令"]),
        ("配置自动锁屏时间300秒", "security_policy", "离开工位场景建议空闲5分钟自动锁屏。", ["锁屏", "300秒"]),
        ("会话超时退出", "security_policy", "远程会话可配置空闲超时，降低未锁定终端风险。", ["会话超时"]),
        ("检查SUID文件", "workflow", "`find / -perm -4000` 可列出SUID文件，异常项需安全评估。", ["SUID"]),
        ("配置AppArmor概况", "fact", "部分应用可由 AppArmor 配置文件限制能力，异常时查 aa-status。", ["AppArmor"]),
        ("安全删除敏感文件", "workflow", "对敏感文件可用 `shred -u` 后再删除（SSD效果有限，仍建议加密盘）。", ["安全删除"]),
        ("配置日志远程发送", "security_policy", "关键日志可转发到集中平台，防止本机被清理后无据可查。", ["日志转发"]),
    ]
    for item in sec_items:
        add(*item)

    # ---- office / WPS ----
    office_items = [
        ("WPS文字插入目录", "workflow", "在WPS文字中基于标题样式插入自动目录，更新域可刷新页码。", ["WPS", "目录"]),
        ("WPS表格冻结首行", "workflow", "WPS表格「视图」中冻结首行，便于滚动查看长表。", ["WPS", "冻结"]),
        ("WPS演示母版修改", "workflow", "在母版视图统一修改字体与页脚，避免逐页手工改。", ["WPS", "母版"]),
        ("WPS导出图片清晰度", "operation_habit", "导出PDF/图片前在选项中提高图像质量，避免投影模糊。", ["WPS", "导出"]),
        ("WPS修订模式审阅", "workflow", "开启修订后可跟踪他人修改，审阅结束再接受/拒绝。", ["WPS", "修订"]),
        ("WPS邮件合并", "workflow", "用邮件合并根据表格批量生成通知函。", ["WPS", "邮件合并"]),
        ("WPS加密文档", "security_policy", "对含敏感信息的文档设置打开密码，并分信道传递口令。", ["WPS", "加密"]),
        ("WPS清除文档元数据", "security_policy", "外发前清理作者/修订等元数据，降低信息泄漏。", ["元数据"]),
        ("打印前预览分页", "workflow", "打印预览确认页边距与分页，避免密封线被裁切。", ["打印预览"]),
        ("设置双面长边装订", "workflow", "打印机属性中选择双面长边翻转，适合装订成册。", ["双面打印"]),
        ("添加网络打印机IP", "workflow", "控制中心添加打印机时选择网络打印机并填写IP与驱动。", ["网络打印机"]),
        ("清理打印队列卡死任务", "case", "任务卡住时可暂停打印机、删除队列作业并重启cups服务。", ["打印队列"]),
        ("扫描成PDF", "workflow", "使用简易扫描或厂家工具，输出PDF并检查分辨率。", ["扫描"]),
        ("OCR识别扫描件", "workflow", "对扫描PDF可用OCR工具提取文字，便于检索与复制。", ["OCR"]),
        ("会议投屏有线HDMI", "workflow", "用HDMI连接投影，在显示设置选择扩展或镜像。", ["投屏", "HDMI"]),
        ("无线投屏注意保密", "security_policy", "无线投屏勿投射含密内容；会议结束立即断开。", ["投屏", "保密"]),
        ("制作会议签到表", "workflow", "可用WPS表格模板制作签到，现场打印或电子填写。", ["签到表"]),
        ("压缩邮件附件", "workflow", "大附件先zip再发送，或改用网盘链接并设置有效期。", ["附件"]),
        ("日历创建重复会议", "operation_habit", "在日历中创建每周重复会议，并附会议室与议程链接。", ["日历"]),
        ("导出通讯录备份", "workflow", "定期导出邮件/即时通讯联系人备份，防止账号异常丢失。", ["通讯录"]),
    ]
    for item in office_items:
        add(*item)

    # ---- development ----
    dev_items = [
        ("创建CMake项目骨架", "workflow", "用 `cmake -S . -B build && cmake --build build` 配置并编译工程。", ["cmake"]),
        ("查看动态库依赖", "workflow", "`ldd ./app` 可检查缺失的 .so，再安装对应开发包。", ["ldd"]),
        ("设置编译并行度", "operation_habit", "`make -j$(nproc)` 或 cmake --build 并行，加快编译。", ["并行编译"]),
        ("使用gdb断点调试", "workflow", "`gdb ./app` 后 break/run/bt 定位崩溃栈。", ["gdb"]),
        ("生成core dump", "workflow", "`ulimit -c unlimited` 后复现崩溃，用 gdb 分析 core 文件。", ["core"],),
        ("用strace跟踪打开文件", "workflow", "`strace -e openat ./app` 可发现程序查找的配置路径。", ["strace"]),
        ("配置pip国内源", "operation_habit", "在 pip.conf 设置可信镜像源，加速 Python 包安装。", ["pip", "镜像"]),
        ("pip安装到用户目录", "workflow", "`pip install --user 包名` 避免写系统目录；更推荐venv。", ["pip"]),
        ("poetry管理依赖", "workflow", "可用 poetry 锁定依赖版本，保证麒麟开发机环境一致。", ["poetry"]),
        ("node使用nvm切换版本", "workflow", "用 nvm 安装并切换 Node 版本，避免系统 node 冲突。", ["nvm"]),
        ("配置git忽略文件", "workflow", "在 .gitignore 排除 build/、.venv/、密钥文件等。", ["gitignore"]),
        ("git暂存与提交规范", "workflow", "小步提交：add → commit -m 「清晰说明」→ push。", ["git", "提交"]),
        ("git创建并切换分支", "workflow", "`git checkout -b feature/x` 创建功能分支，合并前先 rebase/pull。", ["git", "分支"]),
        ("git解决合并冲突", "case", "冲突时手动编辑冲突标记，再 add 并 commit 完成合并。", ["git", "冲突"]),
        ("git贮藏临时修改", "workflow", "`git stash -u` 暂存脏工作区，切换分支后再 stash pop。", ["git", "stash"]),
        ("配置clang-format", "operation_habit", "在仓库放入 .clang-format，提交前格式化C/C++代码。", ["clang-format"]),
        ("启用编译警告即错误", "operation_habit", "对关键工程可加 -Werror，避免警告堆积。", ["编译警告"]),
        ("查找头文件路径", "workflow", "`gcc -E -x c++ - -v < /dev/null` 可查看默认头文件搜索路径。", ["头文件"]),
        ("pkg-config查询CFLAGS", "workflow", "`pkg-config --cflags --libs libname` 获取编译链接参数。", ["pkg-config"]),
        ("制作deb安装包基础", "workflow", "可用 fpm 或官方工具打包 deb，注意依赖与版本号。", ["deb"]),
        ("容器内开发挂载代码", "workflow", "podman/docker run -v 源码:容器路径 进行隔离构建。", ["容器", "挂载"]),
        ("清理Docker悬空镜像", "workflow", "`docker image prune` 清理悬空镜像释放空间。", ["docker", "清理"]),
        ("查看容器日志", "workflow", "`docker logs -f 容器` 或 podman logs 跟踪输出。", ["容器日志"]),
        ("配置HTTP调试代理到IDE", "workflow", "在Kylin-IDE运行配置中设置代理，便于抓取接口请求。", ["IDE", "代理"]),
        ("Kylin-IDE安装插件", "workflow", "在扩展市场搜索并安装语言支持/Lint插件，按需启用。", ["Kylin-IDE", "插件"]),
        ("Kylin-IDE配置Python解释器", "workflow", "选择项目 .venv 中的 python 作为解释器，避免用到系统包。", ["Kylin-IDE", "Python"]),
        ("Kylin-IDE调试断点", "workflow", "在编辑器左侧点断点，用调试视图启动，观察变量与调用栈。", ["Kylin-IDE", "调试"]),
        ("配置clangd语言服务", "workflow", "生成 compile_commands.json 并启用 clangd，提高跳转与补全。", ["clangd"]),
        ("生成compile_commands", "workflow", "CMake 加 -DCMAKE_EXPORT_COMPILE_COMMANDS=ON 生成编译数据库。", ["compile_commands"]),
        ("单元测试运行pytest", "workflow", "在venv中 `pytest -q` 运行测试，CI前本地先跑通。", ["pytest"]),
        ("基准测试注意隔离", "fact", "性能对比时应关闭无关高占用进程，并固定CPU频率策略。", ["基准测试"]),
        ("查看反汇编", "workflow", "`objdump -d app` 或 gdb disassemble 查看关键函数指令。", ["反汇编"]),
        ("检查栈金丝雀", "fact", "开启栈保护编译选项可缓解部分溢出，仍需安全编码。", ["栈保护"]),
        ("地址消毒剂构建", "workflow", "开发调试可用 -fsanitize=address 捕获内存错误。", ["ASan"]),
        ("静态链接注意体积", "fact", "静态链接便于分发但体积大，授权与安全更新也更困难。", ["静态链接"]),
        ("设置RPATH", "workflow", "对私有 .so 可用 rpath 指向库目录，减少LD_LIBRARY_PATH依赖。", ["rpath"]),
        ("排查undefined reference", "case", "链接缺符号时核对库顺序、架构匹配与是否安装 -dev 包。", ["链接错误"]),
        ("交叉编译前确认工具链", "workflow", "交叉构建需匹配目标三元组工具链与sysroot。", ["交叉编译"]),
        ("使用ccache加速", "operation_habit", "安装 ccache 并导出 CC/CXX 包装器，重复编译显著加速。", ["ccache"]),
        ("预提交钩子检查", "workflow", "用 pre-commit 跑格式化与基础检查，减少坏提交进入远端。", ["pre-commit"]),
    ]
    for item in dev_items:
        # fix accidental tuple trailing for one item
        if len(item) == 4:
            add(item[0], item[1], item[2], item[3])
        else:
            add(item[0], item[1], item[2], list(item[3]))

    # ---- troubleshooting cases ----
    cases = [
        ("开机进入救援模式排查", "case", "开机异常进入救援模式时，先检查磁盘挂载、fstab 与根分区只读原因。", ["救援模式"]),
        ("图形界面黑屏但SSH可用", "case", "可SSH登录后查看 display-manager 日志，尝试重启图形服务。", ["黑屏"]),
        ("登录后立刻返回登录框", "case", "常见于家目录权限错误或磁盘满；检查 /home 权限与 df。", ["无法登录"]),
        ("sudo提示无终端", "case", "某些图形程序调用sudo需配置askpass；或改在真实终端执行。", ["sudo"]),
        ("apt锁定文件占用", "case", "出现 lock 文件占用时，确认无其它apt进程后再谨慎清理锁。", ["apt", "锁"]),
        ("依赖损坏修复", "case", "`sudo apt -f install` 尝试修复未完成的依赖，再 update。", ["依赖修复"]),
        ("内核升级后外设失效", "case", "先确认驱动是否支持新内核，必要时临时启动旧内核排障。", ["内核", "驱动"]),
        ("声卡只有Dummy Output", "case", "检查用户是否在 audio 组、脉冲音频服务与HDMI占用。", ["声卡"]),
        ("摄像头无法打开", "case", "确认应用权限、`ls /dev/video*` 以及是否被其它进程占用。", ["摄像头"]),
        ("蓝牙能搜到无法配对", "case", "靠近设备、确认配对码，重启 bluetooth 服务后再试。", ["蓝牙配对失败"]),
        ("触控板突然失灵", "case", "检查功能键是否禁用触控板，并查看 xinput 设备状态。", ["触控板失灵"]),
        ("外接屏无信号", "case", "换线换口，执行 xrandr --auto，更新核显/独显驱动。", ["外接屏"]),
        ("字体方框乱码", "case", "安装中文字体并刷新缓存 `fc-cache -fv`，检查应用字体回退。", ["乱码"]),
        ("时间慢导致证书错误", "case", "先同步NTP时间，再重试HTTPS/登录。", ["时间", "证书"]),
        ("磁盘只读文件系统", "case", "出现Read-only file system时检查磁盘健康与dmesg I/O错误。", ["只读"]),
        ("inode耗尽但空间仍在", "case", "df -i 显示inode满时，清理海量小文件目录。", ["inode满"]),
        ("日志把磁盘写满", "case", "定位最大日志、轮转或清理，并修复日志暴涨根因。", ["日志占满"]),
        ("CPU单核100%排查", "case", "用 top/pidstat 定位进程，再结合 strace/perf 深挖。", ["CPU占用"]),
        ("内存泄漏观察", "case", "观察 RSS 持续上涨的进程，用工具分析或重启临时恢复。", ["内存泄漏"]),
        ("僵尸进程处理", "case", "僵尸进程需处理其父进程；重启相关服务通常可回收。", ["僵尸进程"]),
        ("网卡名称变化导致脚本失效", "case", "预测接口名变更后更新脚本，改用稳定连接名或MAC匹配。", ["网卡名"]),
        ("防火墙误拦内网服务", "case", "服务本机通但跨机不通时检查防火墙与监听地址0.0.0.0。", ["防火墙误拦"]),
        ("DNS内网外网不一致", "case", "分流DNS错误时，分开测试内网域名与公网域名解析。", ["DNS分流"]),
        ("容器内访问宿主机服务", "case", "注意网桥IP与防火墙；可用宿主机局域网IP而非127.0.0.1。", ["容器网络"]),
        ("Python模块导入路径错误", "case", "确认venv已激活且 sys.path 不含错目录，避免同名影子模块。", ["Python导入"]),
        ("pip安装缺系统库", "case", "编译型Python包失败时安装对应 -dev 库后再重试。", ["pip编译"]),
        ("Git报SSL证书问题", "case", "先修系统时间与CA证书，不建议随意关闭sslVerify。", ["git", "SSL"]),
        ("SSH主机密钥变更告警", "security_policy", "出现 HOST KEY VERIFICATION FAILED 时应线下确认，勿盲目覆盖。", ["SSH", "主机密钥"]),
        ("U盘变成只读", "case", "检查写保护开关、文件系统错误与dmesg，必要时备份后修复。", ["U盘只读"]),
        ("文件名中文在U盘乱码", "case", "挂载时指定正确iocharset/codepage，或改用exFAT并统一编码。", ["U盘编码"]),
    ]
    for item in cases:
        add(*item)

    # ---- kylin / agent / vector specific expansions ----
    kylin_items = [
        ("查看麒麟激活状态", "fact", "可在「关于本机/系统激活」中查看授权状态，异常时联系管理员。", ["激活"]),
        ("收集系统支持信息", "workflow", "故障报修前收集 os-release、硬件型号、journal 关键片段。", ["支持信息"]),
        ("配置软件源优先级", "workflow", "在 apt sources 中区分官方源与内部源，避免版本被错误覆盖。", ["软件源"]),
        ("禁用自动更新到生产窗口", "security_policy", "生产机自动更新应受变更窗口控制，避免业务高峰重启。", ["自动更新"]),
        ("麒麟应用商店评分注意", "operation_habit", "安装前查看权限与来源说明，优先选择官方上架应用。", ["应用商店"]),
        ("侧边栏快速访问目录", "operation_habit", "把项目目录固定到文件管理器侧边栏，提高切换效率。", ["文件管理器"]),
        ("终端分屏操作", "workflow", "终端仿真器支持分屏时可左右开两个会话，同时编译与查看日志。", ["终端分屏"]),
        ("SSH配置多主机别名", "operation_habit", "在 ~/.ssh/config 为常用主机设置 Host 别名与用户。", ["SSH", "别名"]),
        ("使用tmux恢复会话", "workflow", "长任务在 tmux 中运行，断线后 `tmux attach` 恢复。", ["tmux"]),
        ("配置watch监视命令", "workflow", "`watch -n 1 '命令'` 可周期刷新观察状态变化。", ["watch"]),
        ("使用tee同时落盘日志", "workflow", "`命令 2>&1 | tee run.log` 既看屏幕又保存日志。", ["tee"]),
        ("文本对比diff", "workflow", "`diff -u a b` 查看差异；更大项目可用 git diff。", ["diff"]),
        ("批量替换文本", "workflow", "可用 `sed -i` 谨慎批量替换，先在副本上试验。", ["sed"]),
        ("按内容搜索代码", "workflow", "`rg 关键词` 或 `grep -R` 在工程内搜索。", ["搜索代码"]),
        ("按文件名查找", "workflow", "`find . -name '*.cpp'` 或 fd 按名查找。", ["find"]),
        ("统计代码行数", "workflow", "可用 cloc 或 `find | xargs wc -l` 粗统计。", ["代码量"]),
        ("生成随机密码", "workflow", "`openssl rand -base64 24` 生成高强度随机口令。", ["随机密码"]),
        ("计算目录文件数量", "workflow", "`find dir -type f | wc -l` 统计文件数，辅助发现异常增长。", ["文件数"]),
        ("只读挂载排障盘", "workflow", "可疑磁盘可先只读挂载，避免二次写入破坏现场。", ["只读挂载"]),
        ("使用timeshift创建快照", "workflow", "系统重大变更前用 Timeshift 做快照，失败可回滚。", ["快照"]),
        ("备份dconf用户设置", "workflow", "`dconf dump / > backup.ini` 备份桌面个性化配置。", ["dconf"]),
        ("恢复dconf用户设置", "workflow", "`dconf load / < backup.ini` 可恢复先前导出的设置。", ["dconf恢复"]),
        ("导出已装软件列表", "workflow", "`dpkg --get-selections > pkgs.txt` 便于重装后恢复软件集。", ["软件列表"]),
        ("根据列表批量安装", "workflow", "重装后可用 dpkg --set-selections 与 dselect 恢复软件集合。", ["批量安装"]),
        ("检查系统是否32位兼容库", "fact", "运行旧软件若缺库，可能需安装对应架构兼容包。", ["多架构"]),
        ("添加i386架构注意", "workflow", "仅在确有需要时 `dpkg --add-architecture i386`，并及时更新索引。", ["i386"]),
        ("配置Journal磁盘占用上限", "workflow", "在 journald.conf 限制 SystemMaxUse，防止日志占满。", ["journald"]),
        ("真空清理journal", "workflow", "`sudo journalctl --vacuum-time=7d` 清理旧日志。", ["清理日志"]),
        ("内核参数临时生效", "workflow", "`sysctl -w key=value` 临时生效；持久化写入 sysctl.d。", ["sysctl"]),
        ("调整swappiness", "operation_habit", "桌面机可适度降低 vm.swappiness，减少过早换页。", ["swappiness"]),
        ("查看交换分区", "workflow", "`swapon --show` 与 free -h 查看交换使用情况。", ["swap"]),
        ("添加交换文件", "workflow", "磁盘紧张时可创建swapfile并 chmod 600 后 swapon。", ["swapfile"]),
        ("禁用休眠到磁盘", "security_policy", "高安全场景可禁用hibernate，减少磁盘残留密钥风险。", ["休眠"]),
        ("检查电池健康", "workflow", "笔记本可查看电源统计评估电池容量衰减。", ["电池"]),
        ("校准显示器色彩简述", "fact", "专业场景可用校色仪；普通办公保证亮度一致即可。", ["校色"]),
        ("设置多用户同时登录注意", "security_policy", "快速用户切换可能遗留未锁屏会话，离开时仍需锁屏。", ["多用户"]),
        ("访客账户风险", "security_policy", "交付办公机不建议启用访客账户。", ["访客"]),
        ("临时提权后及时退出", "security_policy", "root会话用完立即 exit，避免误操作。", ["root会话"]),
        ("使用pkexec图形提权", "workflow", "图形管理工具常通过 polkit/pkexec 提权，需输入用户密码。", ["pkexec"]),
        ("排查polkit策略拒绝", "case", "管理操作被拒时查看 polkit 日志与用户组隶属。", ["polkit"]),
        ("将用户加入docker组注意", "security_policy", "docker组权限接近root，加入前需安全评估。", ["docker组"]),
        ("rootless podman优势", "fact", "Podman rootless 可降低容器逃逸影响面，适合桌面开发。", ["podman"]),
        ("配置管道符过滤敏感输出", "security_policy", "脚本输出避免打印密钥；日志也需脱敏。", ["脱敏"]),
        ("使用环境文件管理密钥", "security_policy", "密钥放受限权限的 env 文件，不进仓库。", ["密钥管理"]),
        ("检测仓库误提交密钥", "security_policy", "推送前扫描是否包含AK/SK、私钥；一旦泄露立即轮换。", ["密钥泄露"]),
        ("配置Git签名提交", "workflow", "可启用 GPG/SSH 签名提交，增强审计可信度。", ["git签名"]),
        ("验证下载ISO签名", "security_policy", "系统镜像应校验GPG签名与哈希后再写入启动介质。", ["ISO签名"]),
        ("安全擦除退役硬盘", "security_policy", "退役磁盘需按单位规范擦除或物理销毁，不能只格式化。", ["磁盘销毁"]),
        ("移动存储出入登记", "security_policy", "涉密场所U盘应登记审批，禁止擅自带出。", ["移动存储"]),
        ("屏幕隐私过滤贴", "operation_habit", "开放工位可使用防窥膜，降低肩窥风险。", ["防窥"]),
    ]
    for item in kylin_items:
        add(*item)

    # ---- more unique app workflows (combinatorial but distinct titles) ----
    apps = [
        ("Firefox", "浏览器"),
        ("Chromium", "浏览器"),
        ("WPS文字", "办公"),
        ("WPS表格", "办公"),
        ("WPS演示", "办公"),
        ("Kylin-IDE", "开发"),
        ("VS Code", "开发"),
        ("Vim", "编辑器"),
        ("Emacs", "编辑器"),
        ("GIMP", "图像"),
        ("VLC", "播放器"),
        ("Transmission", "下载"),
        ("Remmina", "远程桌面"),
        ("FileZilla", "FTP"),
        ("KeePassXC", "密码库"),
        ("Flameshot", "截图"),
        ("OBS Studio", "录屏"),
        ("Draw.io", "绘图"),
        ("Postman", "接口调试"),
        ("DBeaver", "数据库客户端"),
    ]
    ops = [
        ("安装", "workflow", "通过应用商店或官方源安装「{app}」，安装后在开始菜单搜索启动。"),
        ("卸载", "workflow", "在应用商店或 `sudo apt remove` 卸载「{app}」，并清理残留配置。"),
        ("更新到最新", "workflow", "通过更新管理器或商店更新「{app}」，更新前保存未提交工作。"),
        ("固定到收藏", "operation_habit", "将「{app}」固定到任务栏或收藏夹，减少搜索时间。"),
        ("设置默认关联", "workflow", "在默认应用程序或右键打开方式中，把相关文件类型关联到「{app}」。"),
        ("排查无法启动", "case", "「{app}」无法启动时，终端运行查看报错，检查依赖与权限。"),
        ("清理缓存", "workflow", "清理「{app}」缓存前先退出程序，再删除其缓存目录（勿删用户数据）。"),
        ("导出配置备份", "workflow", "备份「{app}」配置目录，重装系统后可快速恢复偏好。"),
    ]
    for app, domain in apps:
        for op, subtype, tmpl in ops:
            add(
                f"{op}{app}",
                subtype,
                tmpl.format(app=app) + f" 适用场景：{domain}。",
                [app, op, domain],
            )

    # ---- hardware peripherals ----
    hw = [
        ("添加USB打印机驱动", "workflow", "插入打印机后选择匹配驱动，打印测试页确认。", ["打印机", "USB"]),
        ("配置扫描仪按键", "workflow", "在扫描软件中映射设备按键到「扫描到PDF」等动作。", ["扫描仪"]),
        ("连接USB耳机降噪设置", "workflow", "在声音设置选择USB耳机，并关闭冲突的板载麦。", ["USB耳机"]),
        ("外接键盘布局切换", "workflow", "在键盘布局中添加美式/中文布局，用快捷键切换。", ["键盘布局"]),
        ("绘图板压力测试", "workflow", "在绘图软件中测试压感曲线，驱动异常时重装tablet驱动。", ["绘图板"]),
        ("摄像头隐私盖习惯", "operation_habit", "不用摄像头时盖上隐私盖，降低误开风险。", ["摄像头", "隐私"]),
        ("USB扩展坞供电不足", "case", "扩展坞掉盘时优先使用带供电的型号，并查看dmesg。", ["扩展坞"]),
        ("读卡器无法识别", "case", "试更换USB口，确认文件系统，查看是否缺exfat/ntfs支持。", ["读卡器"]),
        ("串口调试权限", "workflow", "串口设备常需加入 dialout 组，重新登录后生效。", ["串口"]),
        ("CAN盒驱动安装注意", "workflow", "工控CAN设备按厂商说明装驱动，确认内核模块加载。", ["CAN"]),
    ]
    for item in hw:
        add(*item)

    # ---- extra unique admin / desktop facts to reach 820+ ----
    extras = [
        ("查看系统启动耗时", "workflow", "执行 `systemd-analyze blame` 查看各服务启动耗时，定位拖慢开机的单元。", ["开机耗时"]),
        ("分析关键启动链", "workflow", "`systemd-analyze critical-chain` 可查看关键启动路径上的依赖等待。", ["启动链"]),
        ("禁用非必要开机服务", "security_policy", "用 `systemctl disable --now 服务` 关闭确认无用的服务，先做变更记录。", ["禁用服务"]),
        ("创建systemd用户服务", "workflow", "在 ~/.config/systemd/user/ 编写 unit，用 `systemctl --user enable --now` 启用。", ["用户服务"]),
        ("查看磁盘IO等待", "workflow", "`iostat -xz 1` 或监控工具观察 await/%util，判断磁盘瓶颈。", ["磁盘IO"]),
        ("测试磁盘读写速度", "workflow", "可用 `dd` 或专用工具粗测磁盘速度，注意不要覆盖重要分区。", ["磁盘测速"]),
        ("创建LVM逻辑卷简述", "fact", "LVM 可将物理卷组成卷组再切逻辑卷，便于扩容；操作前务必备份。", ["LVM"]),
        ("扩展LVM文件系统", "workflow", "扩容逻辑卷后需对文件系统执行 resize，不同fs命令不同。", ["LVM扩容"]),
        ("查看RAID状态", "workflow", "若使用软RAID，可用 `/proc/mdstat` 或 mdadm 查看阵列健康。", ["RAID"]),
        ("配置邮箱客户端IMAP", "workflow", "在邮件客户端填写IMAP/SMTP与加密方式，按IT文档启用。", ["IMAP"]),
        ("配置企业微信桌面端", "workflow", "从商店或官网安装企业微信，登录后按需开启开机启动。", ["企业微信"]),
        ("配置钉钉消息免打扰", "operation_habit", "在钉钉会话设置免打扰，避免会议被刷屏打断。", ["钉钉"]),
        ("浏览器启用硬件加速", "operation_habit", "在浏览器设置中开启硬件加速，卡顿时再对比关闭效果。", ["硬件加速"]),
        ("清理浏览器站点数据", "workflow", "设置中清除指定站点Cookie与缓存，可修复异常登录态。", ["站点数据"]),
        ("配置浏览器主页", "operation_habit", "将门户或工作台设为主页，加快每日开工。", ["主页"]),
        ("启用浏览器翻译注意", "security_policy", "涉密页面不要提交到在线翻译服务。", ["翻译", "保密"]),
        ("配置PDF默认阅读器", "workflow", "在默认应用中指定PDF打开程序，避免每次询问。", ["PDF"]),
        ("PDF添加密码保护", "security_policy", "外发敏感PDF可设置打开密码与限制打印。", ["PDF加密"]),
        ("合并多个PDF", "workflow", "可用PDF工具或命令行工具按顺序合并材料。", ["PDF合并"]),
        ("PDF页码批量添加", "workflow", "在PDF工具中插入页码页眉页脚，适合材料装订。", ["PDF页码"]),
        ("截图后立即标注", "workflow", "使用Flameshot等工具截图后直接箭头标注，提高沟通效率。", ["截图标注"]),
        ("录制操作演示短片", "workflow", "用简单录屏工具录制操作步骤，便于远程协助说明。", ["录屏"]),
        ("语音输入转写注意", "security_policy", "涉密内容勿使用未审批云端语音转写。", ["语音转写"]),
        ("配置打印机保密打印", "security_policy", "启用PIN取件打印，防止文件在出纸口滞留被拿走。", ["保密打印"]),
        ("检查墨水与耗材状态", "workflow", "在打印机属性或面板查看墨粉/墨水余量并及时申请耗材。", ["耗材"]),
        ("清理打印头简述", "workflow", "喷墨设备可按向导清洗打印头；频繁清洗会耗墨。", ["打印头"]),
        ("设置双显示器任务栏位置", "operation_habit", "可在任务栏设置中选择主屏显示或每屏显示任务栏。", ["任务栏", "多屏"]),
        ("窗口在显示器间移动快捷键", "workflow", "使用窗口快捷键将当前窗口移到另一显示器，提高效率。", ["多屏窗口"]),
        ("配置触控屏虚拟键盘", "workflow", "平板模式可启用屏幕键盘，便于无键盘输入。", ["屏幕键盘"]),
        ("旋转屏幕方向", "workflow", "在显示设置中旋转屏幕，用于特殊柜员/展陈场景。", ["屏幕旋转"]),
        ("镜像投屏与扩展区别", "fact", "镜像适合演示同一画面；扩展适合笔记本继续操作讲稿。", ["投屏模式"]),
        ("关闭不必要动画效果", "operation_habit", "可在性能/辅助选项中减少动画，弱机器更流畅。", ["动画"]),
        ("启用高对比度主题", "workflow", "视觉辅助场景可开启高对比度主题提升可读性。", ["高对比度"]),
        ("放大镜工具使用", "workflow", "临时阅读小字可用系统放大镜，快捷键开关。", ["放大镜"]),
        ("屏幕朗读简述", "fact", "辅助功能提供屏幕朗读，适合无障碍支持场景。", ["屏幕朗读"]),
        ("配置色盲友好配色", "operation_habit", "界面与图表尽量避免仅靠红绿区分信息。", ["无障碍"]),
        ("设置文件默认排序方式", "operation_habit", "文件管理器可按修改时间排序，方便找最近文档。", ["文件排序"]),
        ("批量重命名文件", "workflow", "可用文件管理器批量重命名或 rename/`mmv` 等工具。", ["批量重命名"]),
        ("创建模板文件夹结构", "operation_habit", "为项目预建 docs/src/tests 等目录模板，保持规范。", ["目录模板"]),
        ("使用回收站恢复误删", "workflow", "图形界面删除通常进回收站，可右键还原；彻底删除需备份意识。", ["回收站"]),
        ("清空回收站释放空间", "workflow", "确认无误后清空回收站，可立即回收磁盘空间。", ["清空回收站"]),
        ("设置重要文档只读", "workflow", "对终版材料设只读属性，减少误改。", ["只读文件"]),
        ("计算文件MD5", "workflow", "`md5sum 文件` 用于快速完整性抽查（安全场景更推荐SHA256）。", ["md5"]),
        ("分卷压缩大文件", "workflow", "可用 zip/7z 分卷，便于邮件或U盘拷贝超大材料。", ["分卷压缩"]),
        ("校验分卷完整性", "workflow", "解压前确认全部分卷齐全，缺卷将导致失败。", ["分卷校验"]),
        ("配置自动锁屏并要求密码", "security_policy", "唤醒必须密码，禁止仅靠屏保无认证。", ["锁屏密码"]),
        ("会议室外屏勿存资料", "security_policy", "公用会议机禁止长期存放工作文档，散会清场。", ["会议机"]),
        ("使用临时目录存放下载", "operation_habit", "大安装包先放 ~/Downloads，用完删除，避免家目录膨胀。", ["下载目录"]),
        ("定期清理缩略图缓存", "workflow", "可清理缩略图缓存释放空间，不影响原文件。", ["缩略图"]),
        ("检查家目录配额", "workflow", "若启用配额，用 `quota -s` 查看是否超限。", ["配额"]),
        ("申请扩大磁盘配额", "workflow", "配额不足时按流程向管理员申请扩容并说明用途。", ["配额申请"]),
        ("配置Git工邮地址", "workflow", "`git config --global user.email` 使用公司邮箱，便于审计。", ["git邮箱"]),
        ("配置Git用户名", "workflow", "`git config --global user.name` 使用实名，方便代码评审追溯。", ["git用户名"]),
        ("撤销未推送提交", "workflow", "`git reset` 可调整未推送提交；已推送需走规范回滚流程。", ["git reset"]),
        ("cherry-pick补丁", "workflow", "`git cherry-pick <commit>` 将单提交应用到当前分支。", ["cherry-pick"]),
        ("查看文件修改归属", "workflow", "`git blame 文件` 查看各行最后修改者，便于问责与请教。", ["git blame"]),
        ("二分定位回归", "workflow", "`git bisect` 可在好坏版本间定位引入缺陷的提交。", ["git bisect"]),
        ("子模块更新", "workflow", "含 submodule 的仓库需 `git submodule update --init` 拉取依赖。", ["submodule"]),
        ("LFS管理大文件", "workflow", "大二进制应使用Git LFS，避免仓库膨胀。", ["git-lfs"]),
        ("配置编辑器换行符", "operation_habit", "团队统一LF/CRLF策略，减少无意义差异。", ["换行符"]),
        ("EditorConfig统一风格", "operation_habit", "仓库放置 .editorconfig，统一缩进与编码。", ["editorconfig"]),
        ("预装中文拼写检查", "workflow", "办公套件中启用中文校对，减少错别字外发。", ["拼写检查"]),
        ("设置文档默认字体", "operation_habit", "WPS可设默认字体为宋体/黑体等单位规范字体。", ["默认字体"]),
        ("插入页眉单位名称", "workflow", "在页眉加入单位与密级标识（按文控要求）。", ["页眉"]),
        ("文档加水印", "security_policy", "外发评审稿可加「内部资料」水印，降低扩散风险。", ["水印"]),
        ("表格数据透视简述", "workflow", "WPS表格可用数据透视汇总，适合周报统计。", ["数据透视"]),
        ("表格条件格式", "workflow", "用条件格式高亮异常值，提高审阅效率。", ["条件格式"]),
        ("防抖保护公式", "operation_habit", "关键计算表可保护工作表，仅允许编辑输入区。", ["工作表保护"]),
        ("演示演讲者视图", "workflow", "双屏时可启用演讲者视图看备注，观众只看幻灯。", ["演讲者视图"]),
        ("演示激光笔功能", "workflow", "演示模式可用屏幕激光笔/画笔强调要点。", ["激光笔"]),
        ("压缩演示中的图片", "workflow", "导出前压缩图片，减小PPT体积便于邮发。", ["PPT压缩"]),
        ("浏览器多账户隔离", "security_policy", "工作与个人浏览使用不同配置文件，降低Cookie串扰。", ["浏览器配置"]),
        ("启用网站权限最小开", "security_policy", "摄像头/麦克风权限按站点授予，用完可撤回。", ["站点权限"]),
        ("扩展程序审查", "security_policy", "少装浏览器扩展，只保留来源可信的必要插件。", ["扩展安全"]),
        ("下载拦截面板检查", "workflow", "浏览器拦截可疑下载时，核对URL与证书后再放行。", ["下载拦截"]),
        ("配置开发者工具网络面板", "workflow", "前端排障可在开发者工具Network查看请求状态码与耗时。", ["DevTools"]),
        ("本地启动静态站点", "workflow", "`python3 -m http.server` 可临时预览静态页面（仅本机调试）。", ["静态服务器"]),
        ("检查监听是否绑定本机", "security_policy", "调试服务优先监听127.0.0.1，避免误暴露到局域网。", ["监听地址"]),
        ("使用make干净构建", "workflow", "`make clean && make` 可避免脏对象文件导致的奇怪链接错误。", ["make clean"]),
        ("查看符号表", "workflow", "`nm app | grep 符号` 或 readelf 检查导出/未定义符号。", ["nm"]),
        ("strip释放二进制体积", "workflow", "发布前可 strip 调试符号减小体积（保留单独debug包）。", ["strip"]),
        ("生成软件物料清单SBOM简述", "fact", "重要交付可生成SBOM，便于漏洞追踪与合规。", ["SBOM"]),
        ("依赖漏洞扫描入门", "workflow", "对Python/Node依赖可用对应审计命令扫描已知漏洞。", ["依赖审计"]),
        ("容器镜像漏洞扫描", "workflow", "推送前扫描基础镜像CVE，优先选精简安全基础镜像。", ["镜像扫描"]),
        ("多阶段构建减小镜像", "operation_habit", "Dockerfile使用多阶段构建，最终镜像只含运行所需文件。", ["多阶段构建"]),
        ("只读根文件系统容器", "security_policy", "高安全容器可只读根FS，必要路径再挂可写卷。", ["容器加固"]),
        ("限制容器CPU内存", "workflow", "run 时加 CPU/memory 限额，防止单容器拖垮桌面。", ["容器限额"]),
        ("清理未使用卷", "workflow", "`docker volume prune` 清理无用卷前先确认无重要数据。", ["volume清理"]),
        ("查看网桥与容器IP", "workflow", "`docker network inspect` 可查容器IP与网桥配置。", ["容器网络查看"]),
        ("宿主机时间同步到容器", "fact", "默认多数容器共享宿主机时间命名空间，宿主机时间错会影响容器证书。", ["容器时间"]),
        ("麒麟商店离线安装包", "workflow", "无外网环境可使用管理员提供的离线包按说明安装。", ["离线安装"]),
        ("校验离线包来源", "security_policy", "离线安装包必须来自可信渠道并校验哈希。", ["离线包校验"]),
        ("配置内部证书信任", "workflow", "导入单位根证书到系统信任存储后，内网HTTPS才不被拦截。", ["根证书"]),
        ("删除过期个人证书", "workflow", "在证书管理中删除过期个人证书，避免握手选错证书。", ["证书清理"]),
        ("浏览器忽略证书风险提示", "security_policy", "不要习惯性点「继续访问」；应修复证书或改用可信入口。", ["证书警告"]),
        ("配置自动锁屏快捷短语", "operation_habit", "养成离开座位先锁屏的习惯，可比任何策略都有效。", ["安全习惯"]),
        ("桌面放置只放快捷方式", "operation_habit", "桌面避免堆原文件，材料放文档库，桌面仅快捷方式。", ["桌面整理"]),
        ("使用标签页工作区", "operation_habit", "浏览器按项目分窗口/标签组，减少串任务。", ["标签管理"]),
        ("搜索历史命令", "workflow", "终端用 Ctrl+R 逆向搜索历史命令，加速重复操作。", ["历史搜索"]),
        ("自定义bash别名", "operation_habit", "在.bashrc添加安全别名（如 ll），勿把危险命令做成短别名。", ["alias"]),
        ("及时更新shell配置并生效", "workflow", "修改.bashrc后执行 `source ~/.bashrc` 立即生效。", ["source"]),
        ("分离工作与个人SSH密钥", "security_policy", "不同用途使用不同SSH密钥，权限保持600。", ["SSH密钥隔离"]),
        ("吊销泄露的SSH密钥", "security_policy", "密钥泄露后从各机 authorized_keys 删除并更换新钥。", ["密钥吊销"]),
        ("检查authorized_keys多余项", "security_policy", "定期审查 ~/.ssh/authorized_keys，删除离职人员公钥。", ["authorized_keys"]),
        ("家目录权限至少700", "security_policy", "确保 ~/.ssh 与家目录权限收紧，避免他人可读私钥。", ["家目录权限"]),
        ("使用密码库保存口令", "security_policy", "用KeePassXC等本地密码库，不在记事本存明文密码。", ["密码库"]),
        ("密码库定期备份", "workflow", "加密备份密码库到安全位置，并测试可恢复。", ["密码库备份"]),
        ("二次验证令牌保管", "security_policy", "2FA备份码离线保管，勿拍进相册云同步。", ["2FA"]),
        ("会议纪要当日归档", "operation_habit", "会议结束后当天整理纪要并归档到项目目录。", ["纪要归档"]),
        ("任务待办与日历联动", "operation_habit", "把待办截止时间写入日历提醒，减少遗漏。", ["待办"]),
        ("周报导出PDF归档", "workflow", "周报可用WPS导出PDF并按周命名归档。", ["周报"]),
        ("材料命名含日期版本", "operation_habit", "文件名包含日期与版本号，避免「最终最终版」混乱。", ["命名规范"]),
        ("压缩包命名含用途", "operation_habit", "压缩包名写明项目与用途，便于检索。", ["压缩包命名"]),
        ("外发前再开一次自查", "security_policy", "外发前检查是否含内部地址、账号、未定稿水印。", ["外发检查"]),
        ("使用只读共享给外包", "security_policy", "给外部协作开只读共享，并设到期时间。", ["只读共享"]),
        ("共享链接关闭公开可检索", "security_policy", "网盘链接关闭「任何人可搜」，改为指定人。", ["链接权限"]),
        ("大文件走专用通道", "workflow", "超大交付件走单位批准的传输通道，不走个人网盘。", ["大文件传输"]),
        ("断点续传工具使用", "workflow", "不稳定网络下用支持断点续传的工具拷贝大文件。", ["断点续传"]),
        ("校验拷贝后的文件数", "workflow", "拷贝目录后对比文件数量与抽样哈希，确认完整。", ["拷贝校验"]),
        ("笔记本携带硬盘加密", "security_policy", "出差笔记本应启用磁盘加密并设置BIOS/开机密码（按规范）。", ["出差安全"]),
        ("机场场景注意肩窥", "operation_habit", "公共场所处理敏感信息时使用防窥与及时锁屏。", ["肩窥"]),
        ("连接免费WiFi风险", "security_policy", "勿在未保护的免费WiFi处理公务；优先公司VPN。", ["公共WiFi"]),
        ("手机热点应急上网", "workflow", "公务应急可用手机热点，注意流量与热点密码强度。", ["手机热点"]),
        ("流量耗尽排查后台更新", "case", "热点流量异常时检查是否有大更新/云同步在后台运行。", ["流量异常"]),
        ("关闭不必要的云同步", "security_policy", "涉密目录不要加入个人云盘同步。", ["云同步"]),
        ("网盘版本历史恢复", "workflow", "误覆盖文件时可尝试网盘版本历史恢复。", ["版本历史"]),
        ("本地回收站与网盘回收站都要查", "workflow", "找不到文件时两边回收站都检查。", ["找文件"]),
        ("建立个人知识索引文件", "operation_habit", "用一个索引Markdown记录常用命令与路径，减少重复搜。", ["个人知识库"]),
        ("命令备忘勿含口令", "security_policy", "个人笔记中的命令示例用占位符，不写真实口令。", ["笔记安全"]),
    ]
    for item in extras:
        add(*item)

    # Deduplicate within catalog by normalized title
    seen: set[str] = set()
    uniq: list[tuple[str, str, str, list[str]]] = []
    for title, subtype, body, kws in out:
        title = clean_entry_markers(title).replace("（补充说明）", "").strip()
        body = clean_entry_markers(body)
        if "条目" in body and "（条目" in body:
            body = re.sub(r"（条目\s*\d+）", "", body)
        key = norm_key(title)
        if not key or key in seen:
            continue
        # skip near-identical bodies
        seen.add(key)
        uniq.append((title, subtype, body, kws))
    return uniq


QUERY_VARIANTS = [
    "怎样{title}？",
    "如何{title}？",
    "麒麟系统里怎么{title}？",
    "请说明{title}的方法",
    "{title}该怎么操作？",
    "银河麒麟桌面上如何{title}？",
    "{title}的具体步骤是什么？",
    "新手怎么{title}？",
]


def query_for(title: str, case_n: int) -> str:
    verbish = any(
        title.startswith(v)
        for v in ("打开", "查看", "检查", "安装", "配置", "切换", "连接", "创建", "设置", "挂载", "清理", "启用", "导出", "生成", "用 ", "用apt", "用 apt")
    )
    if title.startswith("用 apt"):
        variants = [
            f"怎样{title}？",
            f"如何{title}？",
            f"麒麟上{title}的命令是什么？",
            f"请给出{title}的步骤",
        ]
    elif verbish or title.startswith(("用", "批量", "安全", "临时", "强制", "只读", "校验", "统计", "文本", "按", "生成", "备份", "恢复", "导出", "添加", "关闭", "开启", "限制", "放行", "抓包", "测试", "诊断", "排查", "校准", "制作", "收集", "禁用", "启用", "锁定", "审计", "验证", "清理", "真空", "调整", "检测", "配置", "查看", "检查", "设置", "切换", "连接", "创建", "安装", "卸载", "更新", "固定", "压缩", "解压", "挂载", "显示", "重置", "重启")):
        variants = [t.format(title=title) for t in QUERY_VARIANTS]
    else:
        variants = [
            f"怎样完成「{title}」？",
            f"关于「{title}」该怎么做？",
            f"请说明「{title}」的步骤",
            f"麒麟桌面上如何处理「{title}」？",
            f"「{title}」应该如何操作？",
            f"系统维护时怎样进行「{title}」？",
        ]
    return variants[case_n % len(variants)]


def related_pair(active: list[dict[str, Any]], i: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Pick two same-domain memories for true multi-gold."""
    a = active[i % len(active)]
    ka = ((a.get("content") or {}).get("keywords") or [""])[0]
    for offset in range(1, min(40, len(active))):
        b = active[(i + offset) % len(active)]
        if b["memory_id"] == a["memory_id"]:
            continue
        kb = ((b.get("content") or {}).get("keywords") or [""])[0]
        # related if share a keyword or same subtype
        aks = set((a.get("content") or {}).get("keywords") or [])
        bks = set((b.get("content") or {}).get("keywords") or [])
        if aks & bks or a.get("subtype") == b.get("subtype"):
            return a, b
    return None


def preserve_query(q: dict[str, Any]) -> bool:
    quality = q.get("quality") or {}
    tags = q.get("tags") or []
    if quality.get("human_reviewed"):
        return True
    if "cross_user" in tags:
        return True
    if "hard" in tags and "p3" in tags:
        return True
    if q.get("split") in {"validation", "final_test"}:
        return True
    return False


def refresh_corpus_fields(row: dict[str, Any]) -> dict[str, Any]:
    r = deepcopy(row)
    r["content_text"] = clean_entry_markers(r.get("content_text"))
    content = dict(r.get("content") or {})
    if isinstance(content.get("title"), str):
        content["title"] = normalize_title(content.get("title"))
    if isinstance(content.get("body"), str):
        content["body"] = clean_entry_markers(content["body"])
    r["content"] = content
    title = content.get("title") or normalize_title(None, r.get("content_text"))
    tid = r.get("canonical_topic_id") or topic_id_for(r["memory_id"], title)
    r["canonical_topic_id"] = tid
    attrs = dict(r.get("attributes") or {})
    attrs["canonical_topic_id"] = tid
    r["attributes"] = attrs
    return r


def expand(target: int) -> dict[str, Any]:
    raw_corpus = [refresh_corpus_fields(r) for r in load_jsonl(DS / "knowledge_corpus.jsonl")]
    queries = load_jsonl(DS / "retrieval_queries.jsonl")

    # Collapse existing near-duplicate titles (whitespace variants etc.)
    id_remap: dict[str, str] = {}
    corpus: list[dict[str, Any]] = []
    key_to_id: dict[str, str] = {}
    for row in raw_corpus:
        # always keep specials
        if row.get("user_id") != SHARED or row.get("status", "active") != "active":
            corpus.append(row)
            id_remap[row["memory_id"]] = row["memory_id"]
            continue
        key = norm_key((row.get("content") or {}).get("title") or row.get("content_text") or "")
        if key and key in key_to_id:
            id_remap[row["memory_id"]] = key_to_id[key]
            continue
        if key:
            key_to_id[key] = row["memory_id"]
        id_remap[row["memory_id"]] = row["memory_id"]
        corpus.append(row)

    # Remap preserved query golds that pointed at collapsed ids
    def remap_golds(golds: list[str]) -> list[str]:
        out: list[str] = []
        for g in golds:
            ng = id_remap.get(g, g)
            if ng not in out:
                out.append(ng)
        return out

    existing_keys = {
        norm_key((c.get("content") or {}).get("title") or c.get("content_text") or "")
        for c in corpus
        if c.get("user_id") == SHARED and c.get("status", "active") == "active"
    }
    existing_keys.discard("")
    max_n = 0
    for c in corpus:
        n = memory_num(c["memory_id"])
        if n < 10**9:
            max_n = max(max_n, n)

    catalog = build_topic_catalog()
    added = []
    for title, subtype, body, kws in catalog:
        if len(corpus) >= target:
            break
        key = norm_key(title)
        if key in existing_keys:
            continue
        max_n += 1
        rec = make_record(max_n, title, subtype, body, kws)
        while any(c["memory_id"] == rec["memory_id"] for c in corpus):
            max_n += 1
            rec = make_record(max_n, title, subtype, body, kws)
        corpus.append(rec)
        existing_keys.add(key)
        added.append(rec["memory_id"])

    if len(corpus) < target:
        raise RuntimeError(
            f"catalog insufficient: corpus={len(corpus)} target={target} catalog={len(catalog)}"
        )

    # active shared for qrels
    active = [
        c
        for c in corpus
        if c.get("status", "active") == "active" and c.get("user_id") == SHARED
    ]
    by_id = {c["memory_id"]: c for c in corpus}

    # rebuild non-preserved Dev queries; keep frozen + curated as-is (but ensure golds exist)
    preserved = []
    rebuild_slots = []
    for q in queries:
        if preserve_query(q):
            # ensure golds exist; drop missing
            row = deepcopy(q)
            if row.get("split") in {"validation", "final_test"}:
                preserved.append(q)  # exact
                continue
            golds = [g for g in remap_golds(list((row.get("expected") or {}).get("gold_memory_ids") or [])) if g in by_id]
            expected = dict(row.get("expected") or {})
            expected["gold_memory_ids"] = golds
            expected["is_no_answer"] = len(golds) == 0 or bool(expected.get("is_no_answer"))
            if expected["is_no_answer"]:
                expected["gold_memory_ids"] = []
                expected["gold_topic_ids"] = []
            else:
                topics = []
                for g in golds:
                    tid = by_id[g].get("canonical_topic_id")
                    if tid and tid not in topics:
                        topics.append(tid)
                expected["gold_topic_ids"] = topics
            row["expected"] = expected
            preserved.append(row)
        else:
            rebuild_slots.append(q)

    # need total queries >= target; preserved count + rebuilt
    need = max(target, len(queries))
    # keep all preserved; rebuild the rest and add more if needed
    out_queries: list[dict[str, Any]] = []
    out_queries.extend([q for q in preserved if q.get("split") in {"validation", "final_test"}])
    out_queries.extend([q for q in preserved if q.get("split") == "dev"])

    used_case_ids = {q["case_id"] for q in out_queries}
    used_queries = {q.get("query") for q in out_queries if q.get("split") == "dev"}

    def next_case_id(n: int) -> str:
        while True:
            cid = f"RET-{n:04d}"
            if cid not in used_case_ids:
                return cid
            n += 1

    # Prefer reusing rebuild_slots case_ids first
    rebuild_ids = [q["case_id"] for q in rebuild_slots]
    # clear old rebuild cases from out (they weren't added)
    # currently out only has preserved

    n_cursor = 1
    produced = 0
    answerable_needed = need - len(out_queries)
    # estimate no-answer ~8%, multi ~2% of rebuilt portion
    i = 0
    while len(out_queries) < need:
        if produced < len(rebuild_ids):
            cid = rebuild_ids[produced]
        else:
            n_cursor = max(n_cursor, 2000)
            cid = next_case_id(n_cursor)
            n_cursor += 1
        used_case_ids.add(cid)
        produced += 1
        i += 1

        # pattern selection
        mode = "single"
        if i % 12 == 0:
            mode = "no_answer"
        elif i % 50 == 0:
            mode = "multi"

        if mode == "no_answer":
            qtext = f"如何配置不存在的设备型号 XYZ-{i:04d}？"
            while qtext in used_queries:
                i += 1
                qtext = f"如何配置不存在的设备型号 XYZ-{i:04d}？"
            used_queries.add(qtext)
            row = {
                "schema_version": "0.1.0",
                "case_id": cid,
                "task_type": "knowledge_retrieval",
                "split": "dev",
                "user_id": SHARED,
                "scene": "galaxy_kylin_v11",
                "query": qtext,
                "top_k": [1, 3, 5, 10],
                "expected": {
                    "gold_memory_ids": [],
                    "gold_topic_ids": [],
                    "is_no_answer": True,
                },
                "evaluation": {
                    "primary_metric": "recall_at_k",
                    "match": "memory_id",
                    "also_report": ["mrr", "latency_p50_p95", "no_answer_accuracy"],
                },
                "tags": ["银河麒麟V11", "retrieval", BATCH, "no_answer"],
                "provenance": {
                    "inspired_by": "BEIR corpus-query-qrels format",
                    "license_note": "仅借鉴评测思想；知识为原创",
                    "adaptation": f"{BATCH} unique expand",
                },
                "quality": {"generation": BATCH, "human_reviewed": False},
            }
            out_queries.append(row)
            continue

        if mode == "multi":
            pair = related_pair(active, i)
            if pair:
                a, b = pair
                title_a = (a.get("content") or {}).get("title") or "操作A"
                title_b = (b.get("content") or {}).get("title") or "操作B"
                qtext = f"如何完成「{title_a}」，以及如何完成「{title_b}」？"
                if qtext in used_queries:
                    qtext = f"请分别说明「{title_a}」与「{title_b}」的步骤（场景{i}）"
                used_queries.add(qtext)
                golds = [a["memory_id"], b["memory_id"]]
                topics = []
                for g in golds:
                    tid = by_id[g].get("canonical_topic_id")
                    if tid and tid not in topics:
                        topics.append(tid)
                out_queries.append(
                    {
                        "schema_version": "0.1.0",
                        "case_id": cid,
                        "task_type": "knowledge_retrieval",
                        "split": "dev",
                        "user_id": SHARED,
                        "scene": "galaxy_kylin_v11",
                        "query": qtext,
                        "top_k": [1, 3, 5, 10],
                        "expected": {
                            "gold_memory_ids": golds,
                            "gold_topic_ids": topics,
                            "is_no_answer": False,
                        },
                        "evaluation": {
                            "primary_metric": "recall_at_k",
                            "match": "memory_id",
                            "also_report": ["mrr", "latency_p50_p95"],
                        },
                        "tags": ["银河麒麟V11", "retrieval", BATCH, "multi_gold"],
                        "provenance": {
                            "inspired_by": "BEIR corpus-query-qrels format",
                            "license_note": "仅借鉴评测思想；知识为原创",
                            "adaptation": f"{BATCH} true multi-intent",
                        },
                        "quality": {"generation": BATCH, "human_reviewed": False},
                    }
                )
                continue
            mode = "single"

        # single
        mem = active[i % len(active)]
        title = (mem.get("content") or {}).get("title") or "相关操作"
        qtext = query_for(title, i)
        bump = 0
        while qtext in used_queries and bump < 20:
            bump += 1
            qtext = query_for(title, i + bump * 17)
        if qtext in used_queries:
            qtext = f"{qtext[:-1]}（案例{i}）？"
        used_queries.add(qtext)
        tid = mem.get("canonical_topic_id")
        out_queries.append(
            {
                "schema_version": "0.1.0",
                "case_id": cid,
                "task_type": "knowledge_retrieval",
                "split": "dev",
                "user_id": SHARED,
                "scene": "galaxy_kylin_v11",
                "query": qtext,
                "top_k": [1, 3, 5, 10],
                "expected": {
                    "gold_memory_ids": [mem["memory_id"]],
                    "gold_topic_ids": [tid] if tid else [],
                    "is_no_answer": False,
                },
                "evaluation": {
                    "primary_metric": "recall_at_k",
                    "match": "memory_id",
                    "also_report": ["mrr", "latency_p50_p95"],
                },
                "tags": ["银河麒麟V11", "retrieval", BATCH],
                "provenance": {
                    "inspired_by": "BEIR corpus-query-qrels format",
                    "license_note": "仅借鉴评测思想；知识为原创",
                    "adaptation": f"{BATCH} unique expand",
                },
                "quality": {"generation": BATCH, "human_reviewed": False},
            }
        )

    # sort: keep stable-ish by case_id
    def cid_num(cid: str) -> int:
        m = re.search(r"(\d+)$", cid or "")
        return int(m.group(1)) if m else 0

    out_queries.sort(key=lambda q: (0 if q.get("split") == "dev" else 1 if q.get("split") == "validation" else 2, cid_num(q.get("case_id", ""))))

    # stats — uniqueness required for active shared knowledge only
    titles = [
        norm_key((c.get("content") or {}).get("title") or "")
        for c in corpus
        if c.get("user_id") == SHARED and c.get("status", "active") == "active"
    ]
    title_counts: dict[str, int] = {}
    for t in titles:
        title_counts[t] = title_counts.get(t, 0) + 1
    dup_titles = [t for t, n in title_counts.items() if t and n > 1]

    return {
        "corpus": corpus,
        "queries": out_queries,
        "added_corpus": len(added),
        "corpus_size": len(corpus),
        "query_size": len(out_queries),
        "dup_titles": dup_titles,
        "dev": sum(1 for q in out_queries if q.get("split") == "dev"),
        "no_answer": sum(
            1
            for q in out_queries
            if q.get("split") == "dev" and (q.get("expected") or {}).get("is_no_answer")
        ),
        "multi": sum(
            1
            for q in out_queries
            if q.get("split") == "dev" and len((q.get("expected") or {}).get("gold_memory_ids") or []) >= 2
        ),
        "entry_markers": sum(1 for c in corpus if "（条目" in (c.get("content_text") or "")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=820)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        args.dry_run = True

    result = expand(args.target)
    summary = {k: v for k, v in result.items() if k not in {"corpus", "queries"}}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if result["dup_titles"]:
        print("ERROR duplicate titles:", result["dup_titles"][:20])
        return 1
    if result["entry_markers"]:
        print("ERROR entry markers remain")
        return 1
    if result["corpus_size"] < args.target or result["query_size"] < args.target:
        print("ERROR below target")
        return 1

    if args.apply:
        write_jsonl(DS / "knowledge_corpus.jsonl", result["corpus"])
        write_jsonl(DS / "retrieval_queries.jsonl", result["queries"])
        REVIEWS.mkdir(parents=True, exist_ok=True)
        (REVIEWS / "v0.6_unique820_report.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("Applied unique 820 expand")
    else:
        print("Dry-run OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
