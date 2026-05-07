from __future__ import annotations

from pathlib import Path

from ..models import ActionType


def fast_inventory_action_type(user_request: str) -> ActionType | None:
    lowered = user_request.lower()
    if any(marker in lowered for marker in ("不要", "别", "不要打开", "别打开")):
        return None
    if any(marker in lowered for marker in ("http://", "https://", "网站", "网页", "网址", "查询", "搜索")):
        return None
    if any(marker in lowered for marker in ("切换到", "切到", "回到", "聚焦", "focus", "switch to")):
        return ActionType.FOCUS_APP
    if any(marker in lowered for marker in ("打开", "启动", "运行", "open", "launch", "start")):
        return ActionType.OPEN_APP
    return None


def is_unsupported_destructive_file_request(user_request: str) -> bool:
    lowered = user_request.lower()
    if any(marker in lowered for marker in ("如何", "怎么", "how to")):
        return False
    destructive_markers = (
        "删除",
        "清空",
        "清理电脑",
        "清理磁盘",
        "delete",
        "remove",
        "wipe",
        "erase",
        "empty recycle bin",
    )
    file_scope_markers = (
        "文件",
        "文件夹",
        "桌面",
        "回收站",
        "电脑",
        "磁盘",
        "目录",
        "file",
        "folder",
        "desktop",
        "recycle bin",
        "disk",
    )
    return (
        any(marker in lowered for marker in destructive_markers)
        and any(marker in lowered for marker in file_scope_markers)
    )


def is_current_workspace_reference(user_request: str, target: str) -> bool:
    combined = f"{user_request} {target}".lower()
    return any(
        marker in combined
        for marker in (
            "当前项目",
            "当前工程",
            "当前 workspace",
            "current workspace",
            "current project",
        )
    )


def load_prompt(name: str) -> str:
    return (Path(__file__).resolve().parent.parent / "prompts" / name).read_text(encoding="utf-8")
