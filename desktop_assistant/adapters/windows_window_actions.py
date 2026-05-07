from __future__ import annotations

import re

from ..capability.executor import execution_failed, execution_success
from ..models import ActionStep, ActionType, ExecutionStepResult
from .windows_app_keywords import app_window_keywords, append_keyword, useful_window_keyword
from .windows_app_support import process_details
from .windows_app_discovery import ApplicationInventoryStore
from .windows_window_state import WindowManagerProtocol, WindowMatch


class ListWindowsHandler:
    action_type = ActionType.LIST_WINDOWS
    handler_name = "windows.list_windows"

    def __init__(self, window_manager: WindowManagerProtocol) -> None:
        self.window_manager = window_manager

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        if not self.window_manager.is_available():
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Window manager is unavailable; cannot list windows.",
                code="WINDOW_MANAGER_UNAVAILABLE",
                details={"target": action.target},
                remedy="Run on Windows with pywin32 available.",
            )

        limit = int(action.params.get("limit", 50))
        try:
            windows = self.window_manager.list_visible_windows(limit=limit)
            foreground = self.window_manager.get_foreground_window()
        except Exception as exc:  # noqa: BLE001 - Win32 desktop access can be denied
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Window enumeration failed: {type(exc).__name__}: {exc}",
                code="WINDOW_ENUMERATION_FAILED",
                details={
                    "target": action.target,
                    "limit": limit,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                remedy=(
                    "Run from the same interactive Windows desktop/session as the target apps, "
                    "and avoid elevated/non-elevated privilege mismatches."
                ),
            )
        payload = [window_match_payload(match) for match in windows]
        titles = ", ".join(item["title"] for item in payload[:5] if item["title"])
        suffix = f": {titles}" if titles else ""
        return execution_success(
            action,
            step_index,
            f"[{trace_id}] Listed {len(payload)} visible window(s){suffix}",
            metadata={
                "windows": payload,
                "foreground_window": window_match_payload(foreground) if foreground is not None else None,
                "count": len(payload),
                "limit": limit,
            },
        )


class WindowActionHandler:
    def __init__(
        self,
        action_type: ActionType,
        handler_name: str,
        operation: str,
        window_manager: WindowManagerProtocol,
        app_inventory_store: ApplicationInventoryStore,
    ) -> None:
        self.action_type = action_type
        self.handler_name = handler_name
        self.operation = operation
        self.window_manager = window_manager
        self.app_inventory_store = app_inventory_store

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        if not self.window_manager.is_available():
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Window manager is unavailable; cannot {self.operation} window.",
                code="WINDOW_MANAGER_UNAVAILABLE",
                details={"target": action.target, "operation": self.operation},
                remedy="Run on Windows with pywin32 available.",
            )

        try:
            match_result = resolve_window_target(
                action,
                self.app_inventory_store,
                self.window_manager,
                step_index,
                trace_id,
            )
        except Exception as exc:  # noqa: BLE001 - Win32 desktop access can be denied
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Window lookup failed: {type(exc).__name__}: {exc}",
                code="WINDOW_LOOKUP_FAILED",
                details={
                    "target": action.target,
                    "operation": self.operation,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                remedy=(
                    "Run from the same interactive Windows desktop/session as the target app, "
                    "or use list_windows to verify accessible window titles."
                ),
            )
        if isinstance(match_result, ExecutionStepResult):
            return match_result
        match = match_result

        operation = self.operation
        if operation == "focus":
            ok = self.window_manager.focus_window(match)
        elif operation == "minimize":
            ok = self.window_manager.minimize_window(match)
        elif operation == "maximize":
            ok = self.window_manager.maximize_window(match)
        elif operation == "restore":
            ok = self.window_manager.restore_window(match)
        elif operation == "close":
            ok = self.window_manager.close_window(match)
        else:
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Unknown window operation: {operation}",
                code="WINDOW_OPERATION_UNKNOWN",
                details={"operation": operation},
                remedy="Check the window action handler configuration.",
            )

        if not ok:
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Windows rejected {operation} for window: {match.title}",
                code="WINDOW_OPERATION_REJECTED",
                details={"operation": operation, "window": window_match_payload(match)},
                remedy="The window may be protected, stale, minimized to tray, or controlled by another desktop.",
            )

        verb = {
            "focus": "Focused",
            "minimize": "Minimized",
            "maximize": "Maximized",
            "restore": "Restored",
            "close": "Requested close for",
        }[operation]
        return execution_success(
            action,
            step_index,
            f"[{trace_id}] {verb} window: {match.title}",
            metadata={
                "window": window_match_payload(match),
                "operation": operation,
                **_verification_payload(self.window_manager, match, operation),
            },
        )


def resolve_window_target(
    action: ActionStep,
    store: ApplicationInventoryStore,
    window_manager: WindowManagerProtocol,
    step_index: int,
    trace_id: str,
):
    hwnd = target_hwnd(action)
    if hwnd is not None:
        match = window_manager.find_by_hwnd(hwnd)
        if match is not None:
            return match
        return execution_failed(
            action,
            step_index,
            f"[{trace_id}] No visible window found for hwnd: {hwnd}",
            code="WINDOW_NOT_FOUND",
            details={"target": action.target, "hwnd": hwnd},
            remedy="Refresh the window list; the handle may be stale or the window may be closed.",
        )

    target = action.target.strip()
    match_mode = str(action.params.get("match_mode", "auto")).lower()
    app_name = None
    executable_path = None
    title_keywords = window_target_keywords(target)

    if match_mode in {"auto", "app"}:
        try:
            inventory = store.ensure(refresh=False)
            app = inventory.find(target)
        except (FileNotFoundError, OSError, KeyError, ValueError):
            app = None
        if app is not None:
            app_name = app.name
            executable_path = app.executable_path
            title_keywords = app_window_keywords(app.name, app.executable_path or target)
            if executable_path:
                match = window_manager.find_by_executable(executable_path)
                if match is not None:
                    return match

    if match_mode in {"auto", "title", "app"}:
        match = window_manager.find_by_title_keywords(title_keywords)
        if match is not None:
            return match

    process_match = None
    if executable_path:
        process_match = window_manager.find_process_by_executable(executable_path)
    if process_match is None:
        process_match = window_manager.find_process_by_keywords(title_keywords)

    details = {
        "target": target,
        "match_mode": match_mode,
        "app_name": app_name,
        "executable_path": executable_path,
        "title_keywords": title_keywords,
        "process": process_details(process_match),
    }
    if process_match is not None:
        return execution_failed(
            action,
            step_index,
            f"[{trace_id}] Process exists but no visible window matched: {target}",
            code="APP_PROCESS_RUNNING_NO_WINDOW",
            details=details,
            remedy="The app may be in the system tray, hidden behind a launcher, or on another desktop.",
        )
    return execution_failed(
        action,
        step_index,
        f"[{trace_id}] No visible window matched target: {target}",
        code="WINDOW_NOT_FOUND",
        details=details,
        remedy="Use list_windows to inspect current titles, or open the app before managing its window.",
    )


def target_hwnd(action: ActionStep) -> int | None:
    raw_hwnd = action.params.get("hwnd")
    if raw_hwnd not in (None, ""):
        try:
            return int(raw_hwnd)
        except (TypeError, ValueError):
            return None
    target = action.target.strip().lower()
    match = re.fullmatch(r"(?:hwnd[:#]?)?\s*(\d+)", target)
    return int(match.group(1)) if match is not None else None


def window_target_keywords(target: str) -> list[str]:
    keywords: list[str] = []
    lowered = target.strip().lower()
    if lowered:
        append_keyword(keywords, lowered)
    for token in re.findall(r"[a-z0-9.]+|[\u4e00-\u9fff]+", lowered):
        if useful_window_keyword(token):
            append_keyword(keywords, token)
        if re.search(r"[\u4e00-\u9fff]", token) and len(token) > 2:
            for size in (2, 3, 4):
                for index in range(0, len(token) - size + 1):
                    append_keyword(keywords, token[index : index + size])
    return keywords


def window_match_payload(match: WindowMatch) -> dict[str, object]:
    return {
        "hwnd": match.hwnd,
        "title": match.title,
        "process_id": match.process_id,
        "executable_path": match.executable_path,
        "is_minimized": match.is_minimized,
        "is_maximized": match.is_maximized,
    }


def _verification_payload(
    window_manager: WindowManagerProtocol,
    match: WindowMatch,
    operation: str,
) -> dict[str, object]:
    verified = window_manager.find_by_hwnd(match.hwnd, require_visible=False)
    foreground = window_manager.get_foreground_window()
    payload: dict[str, object] = {
        "verification_status": _verification_status(operation, match, verified, foreground),
    }
    if verified is not None:
        payload["verified_window"] = window_match_payload(verified)
    if foreground is not None:
        payload["foreground_window"] = window_match_payload(foreground)
    return payload


def _verification_status(
    operation: str,
    match: WindowMatch,
    verified: WindowMatch | None,
    foreground: WindowMatch | None,
) -> str:
    if operation == "focus":
        if foreground is not None and foreground.hwnd == match.hwnd:
            return "foreground_confirmed"
        return "foreground_unknown" if foreground is None else "foreground_different"
    if operation == "minimize":
        if verified is not None and verified.is_minimized:
            return "minimized_confirmed"
        return "window_missing_after_operation" if verified is None else "minimized_unconfirmed"
    if operation == "maximize":
        if verified is not None and verified.is_maximized:
            return "maximized_confirmed"
        return "window_missing_after_operation" if verified is None else "maximized_unconfirmed"
    if operation == "restore":
        if verified is not None and not verified.is_minimized and not verified.is_maximized:
            return "restored_confirmed"
        return "window_missing_after_operation" if verified is None else "restored_unconfirmed"
    if operation == "close":
        return "close_no_visible_window" if verified is None else "close_requested"
    return "operation_requested"
