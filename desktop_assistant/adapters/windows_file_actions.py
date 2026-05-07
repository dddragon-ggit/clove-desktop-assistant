from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..capability.executor import execution_failed, execution_success
from ..models import ActionStep, ActionType, ExecutionStepResult
from ..projects.store import ProjectCatalogStore


class OpenUrlHandler:
    action_type = ActionType.OPEN_URL
    handler_name = "windows.open_url"

    def __init__(self, open_url: Callable[[str], bool]) -> None:
        self.open_url = open_url

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        target = action.target.strip()
        opened = self.open_url(target)
        if not opened:
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Browser rejected URL: {target}",
                code="BROWSER_OPEN_REJECTED",
                details={"url": target},
                remedy="Check whether a default browser is configured.",
            )
        return execution_success(action, step_index, f"[{trace_id}] Opened URL: {target}")


class OpenFolderHandler:
    action_type = ActionType.OPEN_FOLDER
    handler_name = "windows.open_folder"

    def __init__(self, open_path: Callable[[str], None]) -> None:
        self.open_path = open_path

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        folder = resolve_target_path(action.target)
        if not folder.exists():
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Folder does not exist: {folder}",
                code="FOLDER_NOT_FOUND",
                details={"path": str(folder)},
                remedy="Check the folder path or refresh the plan.",
            )
        if not folder.is_dir():
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Target is not a folder: {folder}",
                code="TARGET_NOT_FOLDER",
                details={"path": str(folder)},
                remedy="Use open_file/read_text_file for files.",
            )
        self.open_path(str(folder))
        return execution_success(action, step_index, f"[{trace_id}] Opened folder: {folder}")


class OpenProjectHandler:
    action_type = ActionType.OPEN_PROJECT
    handler_name = "windows.open_project"

    def __init__(self, open_path: Callable[[str], None], project_catalog_store: ProjectCatalogStore) -> None:
        self.open_path = open_path
        self.project_catalog_store = project_catalog_store

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        direct_path = resolve_target_path(action.target)
        location = self.project_catalog_store.find(action.target)
        folder = Path(location.path).expanduser() if location is not None else direct_path
        if not folder.exists():
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Project or folder does not exist: {folder}",
                code="PROJECT_NOT_FOUND",
                details={
                    "target": action.target,
                    "path": str(folder),
                    "catalog_path": str(self.project_catalog_store.path),
                },
                remedy="Add the project to projects.json or check the folder path.",
            )
        if not folder.is_dir():
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Project target is not a folder: {folder}",
                code="PROJECT_TARGET_NOT_FOLDER",
                details={"target": action.target, "path": str(folder)},
                remedy="Use open_file for files, or correct the project catalog entry.",
            )
        self.open_path(str(folder))
        source = f" via {self.project_catalog_store.path}" if location is not None else ""
        return execution_success(action, step_index, f"[{trace_id}] Opened project/folder{source}: {folder}")


class OpenFileHandler:
    action_type = ActionType.OPEN_FILE
    handler_name = "windows.open_file"

    def __init__(self, open_path: Callable[[str], None]) -> None:
        self.open_path = open_path

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        file_path = resolve_target_path(action.target)
        if not file_path.exists():
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] File does not exist: {file_path}",
                code="FILE_NOT_FOUND",
                details={"path": str(file_path)},
                remedy="Check the file path or refresh the plan.",
            )
        if not file_path.is_file():
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Target is not a file: {file_path}",
                code="TARGET_NOT_FILE",
                details={"path": str(file_path)},
                remedy="Use open_folder/list_folder for folders.",
            )
        self.open_path(str(file_path))
        return execution_success(action, step_index, f"[{trace_id}] Opened file: {file_path}")


def resolve_target_path(target: str) -> Path:
    normalized = target.strip()
    if normalized.lower() == "desktop" or normalized == "桌面":
        return Path.home() / "Desktop"
    return Path(normalized).expanduser()
