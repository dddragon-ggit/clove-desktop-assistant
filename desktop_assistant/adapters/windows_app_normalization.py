from __future__ import annotations

import re
from pathlib import Path


def _display_name_from_executable(name: str) -> str:
    stem = Path(name).stem if name.lower().endswith(".exe") else name
    return stem.replace("_", " ").replace("-", " ").strip()


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def _search_tokens(value: str) -> list[str]:
    normalized = value.lower()
    raw_tokens = [_normalize_name(token) for token in re.findall(r"[a-z0-9.]+|[\u4e00-\u9fff]+", normalized)]
    tokens: list[str] = []
    for token in raw_tokens:
        if len(token) < 2 or _is_generic_search_token(token):
            continue
        if token not in tokens:
            tokens.append(token)
        if re.search(r"[\u4e00-\u9fff]", token) and len(token) > 2:
            for size in (2, 3, 4):
                for index in range(0, len(token) - size + 1):
                    fragment = token[index : index + size]
                    if _is_generic_search_token(fragment):
                        continue
                    if fragment not in tokens:
                        tokens.append(fragment)
    return tokens


def _is_generic_search_token(token: str) -> bool:
    return token in {
        "打开",
        "启动",
        "运行",
        "应用",
        "软件",
        "程序",
        "切换",
        "聚焦",
        "回到",
        "进入",
        "open",
        "launch",
        "app",
        "application",
    }


def _is_uninstall_or_setup_name(name: str) -> bool:
    normalized = _normalize_name(name)
    markers = (
        "uninstall",
        "unins",
        "setup",
        "installer",
        "卸载",
        "安装",
        "cleanup",
    )
    return any(marker in normalized for marker in markers)


def _infer_application_functions(name: str, executable_path: str | None = None) -> tuple[str, ...]:
    haystack = " ".join(part for part in [name, executable_path or ""]).lower()
    rules = [
        ("web_browser", ("chrome", "edge", "firefox", "browser", "brave", "opera", "浏览器")),
        ("writing", ("word", "obsidian", "notion", "typora", "markdown", "写作", "文档")),
        ("spreadsheet", ("excel", "sheet", "spreadsheet", "表格")),
        ("presentation", ("powerpnt", "powerpoint", "slides", "presentation", "演示")),
        ("communication", ("wechat", "weixin", "qq", "teams", "slack", "telegram", "discord", "zoom", "meeting")),
        ("development", ("code", "cursor", "pycharm", "idea", "visual studio", "git", "terminal", "python")),
        ("design", ("photoshop", "illustrator", "figma", "sketch", "designer", "canva")),
        ("media", ("vlc", "player", "music", "video", "spotify", "网易云", "bilibili")),
        ("archive", ("zip", "rar", "7z", "bandizip", "winrar")),
        ("system_tool", ("control", "settings", "manager", "driver", "update", "terminal", "powershell")),
    ]
    functions = [tag for tag, markers in rules if any(marker in haystack for marker in markers)]
    if not functions:
        functions = ["general_app"]
    return tuple(functions)
