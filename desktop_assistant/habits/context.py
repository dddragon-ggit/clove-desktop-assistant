from __future__ import annotations

from pathlib import Path

from ..activity import ActivitySnapshot


def context_label(snapshot: ActivitySnapshot | None) -> str:
    if snapshot is None:
        return ""
    project = snapshot.active_project.name if snapshot.active_project else ""
    file_name = snapshot.active_file.name if snapshot.active_file else ""
    app = snapshot.active_app.name if snapshot.active_app else ""
    focus = _focus_from_file(file_name)
    if project and focus:
        return f"{project} 的 {focus}"
    if project:
        return project
    if file_name:
        return focus or file_name
    return app


def resume_text(snapshot: ActivitySnapshot, *, interrupted: bool = False) -> str:
    label = context_label(snapshot)
    if not label:
        return "查看待办任务清单"
    prefix = "恢复中断：" if interrupted else "继续："
    return f"{prefix}{label}"


def same_meaningful_context(left: ActivitySnapshot | None, right: ActivitySnapshot | None) -> bool:
    if left is None or right is None:
        return False
    left_project = left.active_project.path if left.active_project else ""
    right_project = right.active_project.path if right.active_project else ""
    if left_project and right_project:
        return left_project.lower() == right_project.lower()
    left_file = left.active_file.path or left.active_file.name if left.active_file else ""
    right_file = right.active_file.path or right.active_file.name if right.active_file else ""
    return bool(left_file and right_file and left_file.lower() == right_file.lower())


def meaningful_snapshot(snapshot: ActivitySnapshot | None) -> bool:
    if snapshot is None:
        return False
    return bool(snapshot.active_project or snapshot.active_file)


def _focus_from_file(file_name: str) -> str:
    if not file_name:
        return ""
    path = Path(file_name)
    stem = path.stem
    lowered = file_name.lower()
    if "\\ui\\" in lowered or "/ui/" in lowered or stem in {"app", "styles"}:
        return "UI 设计"
    if path.suffix.lower() in {".md", ".txt"}:
        return f"{stem} 文档"
    if path.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        return f"{stem} 开发"
    return stem
