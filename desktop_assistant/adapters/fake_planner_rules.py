from __future__ import annotations

import re
from urllib.parse import quote_plus

from ..models import ActionType


_URL_PATTERN = re.compile(
    r"(https?://[^\s，。！？、]+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+[^\s，。！？、]*)",
    re.IGNORECASE,
)

_KNOWN_WEBSITE_URLS = {
    "知乎": "https://www.zhihu.com",
    "zhihu": "https://www.zhihu.com",
    "百度": "https://www.baidu.com",
    "baidu": "https://www.baidu.com",
    "b站": "https://www.bilibili.com",
    "bilibili": "https://www.bilibili.com",
    "github": "https://github.com",
}

_OPEN_WEB_MARKERS = ("打开", "访问", "浏览", "进入")
_LOOKUP_MARKERS = ("查询", "搜索", "查找", "天气", "怎么样", "search", "weather", "look up", "find")
_FOCUS_MARKERS = ("切到", "切换到", "回到", "聚焦", "focus", "switch to")
_WINDOW_LIST_MARKERS = ("列出窗口", "当前窗口", "有哪些窗口", "窗口列表", "list windows")
_WINDOW_ACTION_MARKERS = {
    ActionType.MINIMIZE_WINDOW: ("最小化", "隐藏窗口", "minimize"),
    ActionType.MAXIMIZE_WINDOW: ("最大化", "放大窗口", "maximize"),
    ActionType.RESTORE_WINDOW: ("恢复窗口", "还原窗口", "显示窗口", "restore window", "show window"),
    ActionType.CLOSE_WINDOW: ("关闭窗口", "关掉窗口", "close window"),
    ActionType.FOCUS_WINDOW: ("聚焦窗口", "切换窗口", "focus window"),
}
_PROJECT_MARKERS = ("项目", "工程", "文件夹", "目录", "桌面", "下载", "文档", "project", "folder", "downloads")
_APP_MARKERS = ("应用", "软件", "程序", "app", "application")
_LEADING_TARGET_FILLERS = ("一下", "下", "这个", "那个", "网站", "网页", "站点", "网址")


def _requested_replacement_target(text: str) -> str | None:
    patterns = [
        r"改成\s*([A-Za-z0-9_.\-\u4e00-\u9fff ]{1,40})",
        r"换成\s*([A-Za-z0-9_.\-\u4e00-\u9fff ]{1,40})",
        r"instead use\s*([A-Za-z0-9_.\- ]{1,40})",
        r"use\s*([A-Za-z0-9_.\- ]{1,40})\s*instead",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        target = match.group(1).strip(" 。.，,;；")
        if target:
            return target
    return None


def _requested_website_url(text: str) -> str | None:
    explicit_url = _extract_url(text)
    if explicit_url is not None:
        return explicit_url

    target = _extract_open_target(text)
    if target is None:
        return None

    lowered = target.lower()
    for keyword, url in _KNOWN_WEBSITE_URLS.items():
        if keyword in lowered:
            return url

    return f"https://www.baidu.com/s?wd={quote_plus(target)}"


def _requested_lookup_query(text: str) -> str | None:
    lowered = text.lower()
    if not any(marker in lowered for marker in _LOOKUP_MARKERS):
        return None
    query = text.strip(" ，。！？、,.!?;:：")
    return query or None


def _requested_window_action(text: str) -> tuple[ActionType, str] | None:
    lowered = text.lower()
    if any(marker in lowered for marker in _WINDOW_LIST_MARKERS):
        return ActionType.LIST_WINDOWS, "visible"
    for action_type, markers in _WINDOW_ACTION_MARKERS.items():
        for marker in markers:
            marker_index = lowered.find(marker.lower())
            if marker_index < 0:
                continue
            target = text[marker_index + len(marker) :].strip(" ，。！？、,.!?;:：")
            if not target:
                target = text[:marker_index].strip(" ，。！？、,.!?;:：")
            cleaned = _clean_window_target(target)
            if cleaned:
                return action_type, cleaned
    return None


def _requested_focus_target(text: str) -> str | None:
    lowered = text.lower()
    for marker in _FOCUS_MARKERS:
        marker_index = lowered.find(marker.lower())
        if marker_index >= 0:
            target = text[marker_index + len(marker) :].strip(" ，。！？、,.!?;:：")
            return _clean_open_target(target)
    return None


def _requested_project_target(text: str) -> str | None:
    lowered = text.lower()
    if not any(marker in lowered for marker in _PROJECT_MARKERS):
        return None
    if not any(marker in lowered for marker in _OPEN_WEB_MARKERS) and "open" not in lowered:
        return None
    target = _extract_open_target(text)
    if target is None:
        return None
    if target in {"文件夹", "目录", "项目", "工程"}:
        return None
    return target


def _requested_app_target(text: str) -> str | None:
    lowered = text.lower()
    if not any(marker in lowered for marker in _APP_MARKERS):
        return None
    if not any(marker in lowered for marker in _OPEN_WEB_MARKERS) and "open" not in lowered:
        return None
    target = _extract_open_target(text)
    if target is None:
        return None
    if any(marker in target for marker in ("网页", "网站", "网址", "站点")):
        return None
    return _clean_app_target(target)


def _looks_unsafe_request(text: str) -> bool:
    lowered = text.lower()
    shell_like = ("powershell", "cmd", "terminal", "shell", "脚本", "命令", "命令行")
    destructive = ("删除", "清空", "清理电脑", "清理系统", "delete", "remove", "wipe", "format")
    if any(marker in lowered for marker in shell_like):
        return True
    return any(marker in lowered for marker in destructive)


def _extract_url(text: str) -> str | None:
    match = _URL_PATTERN.search(text)
    if match is None:
        return None

    candidate = match.group(1).strip(".,;:)]}>'\"")
    if not candidate.lower().startswith(("http://", "https://")):
        candidate = f"https://{candidate}"
    return candidate


def _extract_open_target(text: str) -> str | None:
    for marker in _OPEN_WEB_MARKERS:
        marker_index = text.find(marker)
        if marker_index >= 0:
            target = text[marker_index + len(marker) :].strip()
            return _clean_open_target(target)

    lowered = text.lower()
    for marker in ("open", "visit", "go to"):
        match = re.search(rf"\b{re.escape(marker)}\b\s+(?P<target>.+)", lowered, re.IGNORECASE)
        if match is not None:
            return _clean_open_target(match.group("target"))

    return None


def _clean_open_target(target: str) -> str | None:
    cleaned = target.strip(" ，。！？、,.!?;:：")
    changed = True
    while changed:
        changed = False
        for filler in _LEADING_TARGET_FILLERS:
            if filler == "下" and cleaned.startswith("下载"):
                continue
            if cleaned.startswith(filler):
                cleaned = cleaned[len(filler) :].strip(" ，。！？、,.!?;:：")
                changed = True

    return cleaned or None


def _clean_app_target(target: str) -> str | None:
    cleaned = _clean_open_target(target)
    if cleaned is None:
        return None
    changed = True
    while changed:
        changed = False
        lowered = cleaned.lower()
        for suffix in ("应用程序", "application", "应用", "软件", "程序", "app"):
            if lowered.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].strip(" ，。！？、,.!?;:：")
                changed = True
                break
    return cleaned or None


def _clean_window_target(target: str) -> str | None:
    cleaned = _clean_open_target(target)
    if cleaned is None:
        return None
    for suffix in ("这个窗口", "窗口", "应用", "软件", "程序", "app"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip(" ，。！？、,.!?;:：")
    return cleaned or "active"
