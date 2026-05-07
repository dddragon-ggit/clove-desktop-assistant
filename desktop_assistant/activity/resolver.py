from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Callable, Iterable

from ..adapters.windows_app_models import ApplicationInventory, DiscoveredApplication
from ..adapters.windows_window_state import WindowMatch
from ..projects.matching import normalize_project_text
from ..projects.models import ProjectLocation
from .models import ActivityApp, ActivityFile, ActivityProject, ActivitySnapshot, ActivityWindow


DOCUMENT_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".ipynb",
    ".jpeg",
    ".jpg",
    ".json",
    ".md",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xls",
    ".xlsx",
    ".yaml",
    ".yml",
}

EXECUTABLE_EXTENSIONS = {".bat", ".cmd", ".com", ".dll", ".exe", ".msi", ".ps1"}


class ActivityResolver:
    """Resolve raw desktop metadata into app/file/project activity."""

    def __init__(
        self,
        *,
        inventory: ApplicationInventory | None = None,
        projects: Iterable[ProjectLocation] = (),
        path_exists: Callable[[Path], bool] | None = None,
        path_is_file: Callable[[Path], bool] | None = None,
        path_is_dir: Callable[[Path], bool] | None = None,
    ) -> None:
        self.inventory = inventory
        self.projects = list(projects)
        self.path_exists = path_exists or (lambda path: path.exists())
        self.path_is_file = path_is_file or (lambda path: path.is_file())
        self.path_is_dir = path_is_dir or (lambda path: path.is_dir())

    def resolve(
        self,
        *,
        window: WindowMatch | None,
        command_line: str = "",
        recent_files: Iterable[ActivityFile] = (),
        captured_at: str | None = None,
        notes: Iterable[str] = (),
    ) -> ActivitySnapshot:
        activity_window = _activity_window(window)
        command_paths = self._command_paths(command_line)
        recent_file_list = list(recent_files)
        active_file = self._resolve_file(window, command_paths, recent_file_list)
        active_app = self._resolve_app(window)
        active_project = self._resolve_project(window, command_paths, active_file)
        return ActivitySnapshot(
            captured_at=captured_at or ActivitySnapshot().captured_at,
            active_window=activity_window,
            active_app=active_app,
            active_file=active_file,
            active_project=active_project,
            recent_files=recent_file_list,
            notes=list(notes),
        )

    def _resolve_app(self, window: WindowMatch | None) -> ActivityApp | None:
        if window is None:
            return None
        app = self._app_by_executable(window.executable_path)
        if app is not None:
            return ActivityApp(
                name=app.name,
                executable_path=app.executable_path or window.executable_path,
                process_id=window.process_id,
                source="inventory_executable",
                confidence="high",
            )
        if self.inventory is not None:
            title_app = self.inventory.find(window.title)
            if title_app is not None:
                return ActivityApp(
                    name=title_app.name,
                    executable_path=title_app.executable_path or "",
                    process_id=window.process_id,
                    source="inventory_title",
                    confidence="medium",
                )
        fallback_name = Path(window.executable_path).stem if window.executable_path else _title_app_guess(window.title)
        if not fallback_name:
            return None
        return ActivityApp(
            name=fallback_name,
            executable_path=window.executable_path,
            process_id=window.process_id,
            source="window_process",
            confidence="low",
        )

    def _resolve_file(
        self,
        window: WindowMatch | None,
        command_paths: list[Path],
        recent_files: list[ActivityFile],
    ) -> ActivityFile | None:
        for candidate in command_paths:
            if not _is_user_file_candidate(candidate):
                continue
            if self.path_is_file(candidate) or _looks_like_document_path(candidate):
                return ActivityFile(
                    name=candidate.name,
                    path=str(candidate),
                    source="process_command_line",
                    confidence="high" if self.path_is_file(candidate) else "medium",
                )
        if window is None:
            return None
        title = window.title
        recent = _recent_file_from_title(title, recent_files)
        if recent is not None:
            return recent.model_copy(update={"source": "window_title_recent_file", "confidence": "high"})
        title_name = _file_name_from_title(title)
        if title_name:
            return ActivityFile(
                name=title_name,
                path="",
                source="window_title",
                confidence="low",
            )
        return None

    def _resolve_project(
        self,
        window: WindowMatch | None,
        command_paths: list[Path],
        active_file: ActivityFile | None,
    ) -> ActivityProject | None:
        file_path = Path(active_file.path) if active_file and active_file.path else None
        if file_path is not None:
            project = self._project_containing(file_path)
            if project is not None:
                return _activity_project(project, "file_path", "high")
        for candidate in command_paths:
            if self.path_is_dir(candidate):
                project = self._project_containing(candidate) or self._project_by_exact_path(candidate)
                if project is not None:
                    return _activity_project(project, "process_command_line", "high")
        if window is not None:
            title_project = self._project_from_title(window.title)
            if title_project is not None:
                return _activity_project(title_project, "window_title", "medium")
        return None

    def _command_paths(self, command_line: str) -> list[Path]:
        paths: list[Path] = []
        for raw in _path_tokens(command_line):
            candidate = Path(raw.strip("\"' "))
            if candidate in paths:
                continue
            if self.path_exists(candidate) or _looks_like_document_path(candidate):
                paths.append(candidate)
        return paths

    def _app_by_executable(self, executable_path: str) -> DiscoveredApplication | None:
        if self.inventory is None or not executable_path:
            return None
        target = _normalize_path_text(executable_path)
        for app in self.inventory.applications:
            if app.executable_path and _normalize_path_text(app.executable_path) == target:
                return app
        return None

    def _project_containing(self, path: Path) -> ProjectLocation | None:
        target = _normalize_path_text(str(path))
        best: ProjectLocation | None = None
        best_length = -1
        for project in self.projects:
            project_path = _normalize_path_text(project.path)
            if target == project_path or target.startswith(project_path.rstrip("\\/") + "\\"):
                if len(project_path) > best_length:
                    best = project
                    best_length = len(project_path)
        return best

    def _project_by_exact_path(self, path: Path) -> ProjectLocation | None:
        target = _normalize_path_text(str(path))
        for project in self.projects:
            if _normalize_path_text(project.path) == target:
                return project
        return None

    def _project_from_title(self, title: str) -> ProjectLocation | None:
        normalized_title = normalize_project_text(title)
        best: ProjectLocation | None = None
        best_score = 0
        for project in self.projects:
            normalized_name = normalize_project_text(project.name)
            if not normalized_name:
                continue
            score = 0
            if normalized_name in normalized_title:
                score += 80
            for token in normalized_name.split():
                if len(token) >= 3 and token in normalized_title:
                    score += 10
            if score > best_score:
                best = project
                best_score = score
        return best if best_score >= 40 else None


def _activity_window(window: WindowMatch | None) -> ActivityWindow | None:
    if window is None:
        return None
    return ActivityWindow(
        hwnd=window.hwnd,
        title=window.title,
        process_id=window.process_id,
        executable_path=window.executable_path,
        is_minimized=window.is_minimized,
        is_maximized=window.is_maximized,
    )


def _activity_project(project: ProjectLocation, source: str, confidence: str) -> ActivityProject:
    return ActivityProject(
        name=project.name,
        path=project.path,
        kind=project.kind,
        source=source,
        confidence=confidence,
    )


def _path_tokens(command_line: str) -> list[str]:
    if not command_line.strip():
        return []
    tokens: list[str] = []
    for match in re.finditer(r'"([^"]+)"|\'([^\']+)\'', command_line):
        value = match.group(1) or match.group(2) or ""
        if _looks_like_path_text(value):
            tokens.append(value)
    try:
        split_tokens = shlex.split(command_line, posix=False)
    except ValueError:
        split_tokens = []
    for token in split_tokens:
        cleaned = token.strip("\"'")
        if _looks_like_path_text(cleaned):
            tokens.append(cleaned)
    for match in re.finditer(r"(?i)\b[a-z]:\\[^\s\"']+", command_line):
        tokens.append(match.group(0).rstrip("),;"))
    unique: list[str] = []
    for token in tokens:
        if token not in unique:
            unique.append(token)
    return unique


def _looks_like_path_text(value: str) -> bool:
    return bool(re.match(r"(?i)^[a-z]:\\", value.strip())) or value.startswith("\\\\")


def _looks_like_document_path(path: Path) -> bool:
    return path.suffix.lower() in DOCUMENT_EXTENSIONS


def _is_user_file_candidate(path: Path) -> bool:
    return path.suffix.lower() not in EXECUTABLE_EXTENSIONS and (
        _looks_like_document_path(path) or bool(path.suffix)
    )


def _recent_file_from_title(title: str, recent_files: list[ActivityFile]) -> ActivityFile | None:
    lowered = title.lower()
    for record in recent_files:
        names = [record.name.lower()]
        if record.path:
            names.append(Path(record.path).name.lower())
        stem = Path(record.name).stem.lower()
        if len(stem) >= 3:
            names.append(stem)
        if any(name and name in lowered for name in names):
            return record
    return None


def _file_name_from_title(title: str) -> str:
    pattern = r"([\w\u4e00-\u9fff .()\[\]-]+\.(?:csv|docx?|ipynb|jpe?g|json|md|pdf|png|pptx?|py|toml|tsx?|txt|xlsx?|ya?ml))"
    match = re.search(pattern, title, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _title_app_guess(title: str) -> str:
    parts = [part.strip() for part in re.split(r"\s[-|—–]\s", title) if part.strip()]
    return parts[-1] if parts else title.strip()


def _normalize_path_text(value: str) -> str:
    return str(Path(value)).replace("/", "\\").rstrip("\\").lower()
