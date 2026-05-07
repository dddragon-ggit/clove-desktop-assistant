from __future__ import annotations

import os
import webbrowser
from collections.abc import Callable

from ..capabilities import CapabilityRegistry
from ..capability.executor import CapabilityExecutor, SimulatedCapabilityHandler
from ..capability.store import CapabilityStore
from ..models import ActionStep, ActionType, ExecutionStepResult
from ..projects.store import ProjectCatalogStore
from ..todo import TodoStore
from .todo_actions import CreateReminderHandler, ShowTasksHandler
from .web_query import AnswerQueryHandler
from .windows_app_actions import (
    FocusAppHandler,
    OpenAppHandler,
    app_launch_targets as _app_launch_targets,
    app_window_keywords as _app_window_keywords,
    is_blocked_app_launch as _is_blocked_app_launch,
    process_details as _process_details,
    resolve_inventory_app as _resolve_inventory_app,
    validate_app_executable as _validate_app_executable,
    wait_for_app_confirmation as _wait_for_app_confirmation,
)
from .windows_app_discovery import ApplicationInventoryStore
from .windows_file_actions import (
    OpenFileHandler,
    OpenFolderHandler,
    OpenProjectHandler,
    OpenUrlHandler,
    resolve_target_path as _resolve_target_path,
)
from .windows_window_actions import (
    ListWindowsHandler,
    WindowActionHandler,
    resolve_window_target as _resolve_window_target,
    target_hwnd as _target_hwnd,
    window_match_payload as _window_match_payload,
    window_target_keywords as _window_target_keywords,
)
from .windows_window_state import NullWindowManager, WindowManagerProtocol, WindowsWindowManager


class WindowsExecutor:
    """Windows executor assembled from capability handlers."""

    def __init__(
        self,
        *,
        open_url: Callable[[str], bool] | None = None,
        open_path: Callable[[str], None] | None = None,
        app_inventory_store: ApplicationInventoryStore | None = None,
        project_catalog_store: ProjectCatalogStore | None = None,
        todo_store: TodoStore | None = None,
        capability_registry: CapabilityRegistry | None = None,
        window_manager: WindowManagerProtocol | None = None,
    ) -> None:
        self.open_url = open_url or webbrowser.open
        self.open_path = open_path or self._default_open_path
        self.app_inventory_store = app_inventory_store or ApplicationInventoryStore()
        self.project_catalog_store = project_catalog_store or ProjectCatalogStore()
        self.todo_store = todo_store or TodoStore()
        self.window_manager = window_manager or (
            WindowsWindowManager() if open_path is None else NullWindowManager()
        )
        self.capability_registry = capability_registry or CapabilityStore().ensure(
            available_handler_names=self.available_handler_names()
        )
        self.dispatcher = CapabilityExecutor(
            handlers=[
                AnswerQueryHandler(),
                OpenUrlHandler(self.open_url),
                OpenProjectHandler(self.open_path, self.project_catalog_store),
                OpenFolderHandler(self.open_path),
                OpenFileHandler(self.open_path),
                OpenAppHandler(self.open_path, self.app_inventory_store, self.window_manager),
                FocusAppHandler(self.app_inventory_store, self.window_manager),
                ListWindowsHandler(self.window_manager),
                WindowActionHandler(
                    ActionType.FOCUS_WINDOW,
                    "windows.focus_window",
                    "focus",
                    self.window_manager,
                    self.app_inventory_store,
                ),
                WindowActionHandler(
                    ActionType.MINIMIZE_WINDOW,
                    "windows.minimize_window",
                    "minimize",
                    self.window_manager,
                    self.app_inventory_store,
                ),
                WindowActionHandler(
                    ActionType.MAXIMIZE_WINDOW,
                    "windows.maximize_window",
                    "maximize",
                    self.window_manager,
                    self.app_inventory_store,
                ),
                WindowActionHandler(
                    ActionType.RESTORE_WINDOW,
                    "windows.restore_window",
                    "restore",
                    self.window_manager,
                    self.app_inventory_store,
                ),
                WindowActionHandler(
                    ActionType.CLOSE_WINDOW,
                    "windows.close_window",
                    "close",
                    self.window_manager,
                    self.app_inventory_store,
                ),
                ShowTasksHandler(self.todo_store),
                CreateReminderHandler(self.todo_store),
                SimulatedCapabilityHandler(ActionType.START_FOCUS_TIMER),
            ],
            capability_registry=self.capability_registry,
        )

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        return self.dispatcher.execute(action, step_index, trace_id)

    @classmethod
    def available_handler_names(cls) -> set[str]:
        return {
            AnswerQueryHandler.handler_name,
            OpenUrlHandler.handler_name,
            OpenProjectHandler.handler_name,
            OpenFolderHandler.handler_name,
            OpenFileHandler.handler_name,
            OpenAppHandler.handler_name,
            FocusAppHandler.handler_name,
            ListWindowsHandler.handler_name,
            "windows.focus_window",
            "windows.minimize_window",
            "windows.maximize_window",
            "windows.restore_window",
            "windows.close_window",
            ShowTasksHandler.handler_name,
            CreateReminderHandler.handler_name,
            SimulatedCapabilityHandler.handler_name,
        }

    @staticmethod
    def _default_open_path(path: str) -> None:
        if not hasattr(os, "startfile"):
            raise OSError("os.startfile is only available on Windows.")
        os.startfile(path)  # type: ignore[attr-defined]


__all__ = [
    "WindowsExecutor",
    "OpenUrlHandler",
    "OpenProjectHandler",
    "OpenFolderHandler",
    "OpenFileHandler",
    "OpenAppHandler",
    "FocusAppHandler",
    "ListWindowsHandler",
    "WindowActionHandler",
    "ShowTasksHandler",
    "CreateReminderHandler",
]
