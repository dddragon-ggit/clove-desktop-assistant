from __future__ import annotations

import time
from pathlib import Path

from .windows_window_state import ProcessMatch, WindowManagerProtocol, WindowMatch


def wait_for_app_confirmation(
    window_manager: WindowManagerProtocol,
    *,
    executable: Path,
    title_keywords: list[str],
    timeout_seconds: float,
) -> tuple[WindowMatch | None, str, ProcessMatch | None]:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    process_match: ProcessMatch | None = None
    process_seen_at: float | None = None
    process_window_grace_seconds = min(
        timeout_seconds,
        max(0.0, float(getattr(window_manager, "process_window_grace_seconds", timeout_seconds))),
    )
    poll_interval_seconds = max(0.0, float(getattr(window_manager, "poll_interval_seconds", 0.25)))
    executable_text = str(executable)
    while time.monotonic() <= deadline:
        match = window_manager.find_by_executable(executable_text)
        if match is not None:
            return match, "executable", process_match

        match = window_manager.find_by_title_keywords(title_keywords)
        if match is not None:
            return match, "window title", process_match

        if process_match is None:
            process_match = window_manager.find_process_by_executable(executable_text)
        if process_match is None:
            process_match = window_manager.find_process_by_keywords(title_keywords)
        if process_match is not None and process_seen_at is None:
            process_seen_at = time.monotonic()
        if process_seen_at is not None and time.monotonic() - process_seen_at >= process_window_grace_seconds:
            break
        if poll_interval_seconds:
            time.sleep(poll_interval_seconds)
    return None, "", process_match
