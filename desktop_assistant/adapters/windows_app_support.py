from __future__ import annotations

from pathlib import Path

from ..capability.executor import execution_failed
from ..capability.validation import SHELL_LIKE_APP_MARKERS
from ..models import ActionStep, ExecutionStepResult
from .windows_app_discovery import ApplicationInventoryStore, DiscoveredApplication
from .windows_window_state import ProcessMatch


def resolve_inventory_app(action: ActionStep, store: ApplicationInventoryStore, step_index: int, trace_id: str):
    inventory = store.ensure(refresh=False)
    app = inventory.find(action.target)
    if app is None or not app.executable_path:
        return execution_failed(
            action,
            step_index,
            f"[{trace_id}] App is not in inventory: {action.target}",
            code="APP_NOT_IN_INVENTORY",
            details={"target": action.target, "inventory_path": str(store.path)},
            remedy="Refresh app_inventory.json or check whether the app is installed.",
        )
    return app


def app_launch_targets(app: DiscoveredApplication, executable: Path) -> list[Path]:
    targets: list[Path] = []
    if app.raw_target:
        raw_target = Path(app.raw_target)
        if raw_target.suffix.lower() == ".lnk" and raw_target.exists():
            targets.append(raw_target)
    if executable not in targets:
        targets.append(executable)
    return targets


def process_details(process_match: ProcessMatch | None) -> dict[str, object] | None:
    if process_match is None:
        return None
    return {
        "process_id": process_match.process_id,
        "executable_path": process_match.executable_path,
    }


def validate_app_executable(
    action: ActionStep,
    app_name: str,
    executable_path: str,
    step_index: int,
    trace_id: str,
):
    executable = Path(executable_path).expanduser()
    if not executable.is_absolute():
        return execution_failed(
            action,
            step_index,
            f"[{trace_id}] App executable is not absolute: {app_name}",
            code="APP_EXECUTABLE_NOT_ABSOLUTE",
            details={"app_name": app_name, "executable_path": executable_path},
            remedy="Refresh app_inventory.json so the app has an absolute executable path.",
        )
    if executable.suffix.lower() != ".exe":
        return execution_failed(
            action,
            step_index,
            f"[{trace_id}] App executable is not an .exe: {executable}",
            code="APP_EXECUTABLE_NOT_EXE",
            details={"app_name": app_name, "executable_path": str(executable)},
            remedy="Refresh app_inventory.json or choose a Windows executable target.",
        )
    if not executable.exists() or not executable.is_file():
        return execution_failed(
            action,
            step_index,
            f"[{trace_id}] App executable does not exist: {executable}",
            code="APP_EXECUTABLE_MISSING",
            details={"app_name": app_name, "executable_path": str(executable)},
            remedy="Refresh app_inventory.json or reinstall the application.",
        )
    return executable


def is_blocked_app_launch(name: str, executable_path: str) -> bool:
    lowered = f"{name} {executable_path}".lower()
    return any(marker in lowered for marker in SHELL_LIKE_APP_MARKERS)
