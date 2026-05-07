from __future__ import annotations

from collections.abc import Callable

from ..capability.executor import execution_failed, execution_success
from ..models import ActionStep, ActionType, ExecutionStepResult
from .windows_app_confirmation import wait_for_app_confirmation
from .windows_app_discovery import ApplicationInventoryStore
from .windows_app_keywords import app_window_keywords
from .windows_app_support import (
    app_launch_targets,
    is_blocked_app_launch,
    process_details,
    resolve_inventory_app,
    validate_app_executable,
)
from .windows_window_state import ProcessMatch, WindowManagerProtocol, WindowMatch


class OpenAppHandler:
    action_type = ActionType.OPEN_APP
    handler_name = "windows.open_app"

    def __init__(
        self,
        open_path: Callable[[str], None],
        app_inventory_store: ApplicationInventoryStore,
        window_manager: WindowManagerProtocol,
    ) -> None:
        self.open_path = open_path
        self.app_inventory_store = app_inventory_store
        self.window_manager = window_manager

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        app_result = resolve_inventory_app(action, self.app_inventory_store, step_index, trace_id)
        if isinstance(app_result, ExecutionStepResult):
            return app_result
        app = app_result
        if is_blocked_app_launch(app.name, app.executable_path):
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] App launch is blocked by safety policy: {app.name}",
                code="APP_LAUNCH_BLOCKED",
                details={"app_name": app.name, "executable_path": app.executable_path},
                remedy="This shell-like app is intentionally blocked by policy.",
            )

        executable_result = validate_app_executable(action, app.name, app.executable_path, step_index, trace_id)
        if isinstance(executable_result, ExecutionStepResult):
            return executable_result
        executable = executable_result

        title_keywords = app_window_keywords(app.name, str(executable))
        existing = self.window_manager.find_by_executable(str(executable))
        if existing is None:
            existing = self.window_manager.find_by_title_keywords(title_keywords)
        if existing is not None:
            focused = self.window_manager.focus_window(existing)
            focus_text = "focused" if focused else "focus was rejected by Windows"
            return execution_success(
                action,
                step_index,
                f"[{trace_id}] App {app.name} is already running; {focus_text}: {existing.title}",
            )

        launch_attempts: list[dict[str, str]] = []
        match: WindowMatch | None = None
        process_match: ProcessMatch | None = None
        for launch_target in app_launch_targets(app, executable):
            launch_attempts.append(
                {
                    "target": str(launch_target),
                    "kind": "shortcut" if launch_target.suffix.lower() == ".lnk" else "executable",
                }
            )
            self.open_path(str(launch_target))
            if not self.window_manager.is_available():
                return execution_success(
                    action,
                    step_index,
                    f"[{trace_id}] Launched app {app.name}: {executable}. Window verification is unavailable.",
                )

            match, verification_method, process_match = wait_for_app_confirmation(
                self.window_manager,
                executable=executable,
                title_keywords=title_keywords,
                timeout_seconds=8.0,
            )
            if match is not None:
                self.window_manager.focus_window(match)
                return execution_success(
                    action,
                    step_index,
                    f"[{trace_id}] Launched and verified app {app.name} by {verification_method}: {match.title}",
                )

        details = {
            "app_name": app.name,
            "executable_path": str(executable),
            "launch_attempts": launch_attempts,
            "process": process_details(process_match),
            "title_keywords": title_keywords,
            "verification_timeout_seconds": 8.0,
        }
        if process_match is not None:
            return execution_failed(
                action,
                step_index,
                (
                    f"[{trace_id}] App process is running but no visible window was detected: "
                    f"{app.name}"
                ),
                code="APP_PROCESS_RUNNING_NO_WINDOW",
                details=details,
                remedy=(
                    "The launcher or app appears to be running in the background. "
                    "Open it manually from the system tray, wait for login/update UI, or refresh app_inventory.json."
                ),
            )
        return execution_failed(
            action,
            step_index,
            f"[{trace_id}] App launch was requested but no visible window was detected: {app.name}",
            code="APP_LAUNCH_NOT_VERIFIED",
            details=details,
            remedy=(
                "No matching process or window was detected after launch. "
                "Check whether the app is installed, blocked by login/update UI, or has a stale shortcut."
            ),
        )


class FocusAppHandler:
    action_type = ActionType.FOCUS_APP
    handler_name = "windows.focus_app"

    def __init__(self, app_inventory_store: ApplicationInventoryStore, window_manager: WindowManagerProtocol) -> None:
        self.app_inventory_store = app_inventory_store
        self.window_manager = window_manager

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        if not self.window_manager.is_available():
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Window manager is unavailable.",
                code="WINDOW_MANAGER_UNAVAILABLE",
                details={"target": action.target},
                remedy="Run on Windows with pywin32 available, or use open_app to launch the app.",
            )

        app_result = resolve_inventory_app(action, self.app_inventory_store, step_index, trace_id)
        if isinstance(app_result, ExecutionStepResult):
            return app_result
        executable_result = validate_app_executable(
            action,
            app_result.name,
            app_result.executable_path,
            step_index,
            trace_id,
        )
        if isinstance(executable_result, ExecutionStepResult):
            return executable_result

        title_keywords = app_window_keywords(app_result.name, str(executable_result))
        match = self.window_manager.find_by_executable(str(executable_result))
        verification_method = "executable"
        if match is None:
            match = self.window_manager.find_by_title_keywords(title_keywords)
            verification_method = "window title"
        if match is None:
            process_match = self.window_manager.find_process_by_executable(str(executable_result))
            if process_match is None:
                process_match = self.window_manager.find_process_by_keywords(title_keywords)
            details = {
                "app_name": app_result.name,
                "executable_path": str(executable_result),
                "process": process_details(process_match),
                "title_keywords": title_keywords,
            }
            if process_match is not None:
                return execution_failed(
                    action,
                    step_index,
                    f"[{trace_id}] App process is running but no visible window was found: {app_result.name}",
                    code="APP_PROCESS_RUNNING_NO_WINDOW",
                    details=details,
                    remedy="The app appears to be running in the background; open its window manually or retry later.",
                )
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] No visible window found for app: {app_result.name}",
                code="APP_WINDOW_NOT_FOUND",
                details=details,
                remedy="Launch the app first, then use focus_app.",
            )
        if not self.window_manager.focus_window(match):
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Windows rejected focusing app window: {app_result.name}",
                code="APP_FOCUS_REJECTED",
                details={"app_name": app_result.name, "window_title": match.title},
                remedy="Click the app manually or retry after the assistant window is not active.",
            )
        return execution_success(
            action,
            step_index,
            f"[{trace_id}] Focused app {app_result.name} by {verification_method}: {match.title}",
        )
