from __future__ import annotations

import time
from collections.abc import Iterable

from .windows_window_models import ProcessMatch, WindowMatch
from .windows_window_utils import normalize_keywords, normalize_path


class WindowsWindowManager:
    """Win32 window lookup/focus helper with graceful dependency fallback."""

    def __init__(self) -> None:
        try:
            import win32api  # type: ignore[import-not-found]
            import win32con  # type: ignore[import-not-found]
            import win32gui  # type: ignore[import-not-found]
            import win32process  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001 - optional desktop integration
            self.win32api = None
            self.win32con = None
            self.win32gui = None
            self.win32process = None
        else:
            self.win32api = win32api
            self.win32con = win32con
            self.win32gui = win32gui
            self.win32process = win32process

    def is_available(self) -> bool:
        return bool(self.win32api and self.win32gui and self.win32process and self.win32con)

    def find_by_executable(self, executable_path: str) -> WindowMatch | None:
        if not self.is_available():
            return None
        target = normalize_path(executable_path)
        if not target:
            return None

        matches: list[WindowMatch] = []

        def callback(hwnd: int, _extra: object) -> bool:
            if not self._is_visible_window(hwnd):
                return True
            process_id = self.win32process.GetWindowThreadProcessId(hwnd)[1]
            process_path = self._process_executable(process_id)
            if process_path and normalize_path(process_path) == target:
                matches.append(self._window_match(hwnd, process_id=process_id))
            return True

        self.win32gui.EnumWindows(callback, None)
        return matches[0] if matches else None

    def list_visible_windows(self, limit: int = 50) -> list[WindowMatch]:
        if not self.is_available():
            return []
        safe_limit = max(1, min(int(limit), 100))
        matches: list[WindowMatch] = []

        def callback(hwnd: int, _extra: object) -> bool:
            if len(matches) >= safe_limit:
                return False
            if not self._is_visible_window(hwnd):
                return True
            process_id = self.win32process.GetWindowThreadProcessId(hwnd)[1]
            matches.append(self._window_match(hwnd, process_id=process_id))
            return True

        self.win32gui.EnumWindows(callback, None)
        return matches

    def focus_window(self, match: WindowMatch) -> bool:
        if not self.is_available():
            return False
        try:
            if self.win32gui.IsIconic(match.hwnd):
                self.win32gui.ShowWindow(match.hwnd, self.win32con.SW_RESTORE)
            result = self.win32gui.SetForegroundWindow(match.hwnd)
            if not result:
                return False
        except Exception:  # noqa: BLE001 - foreground lock rules can reject focus
            return False
        return True

    def minimize_window(self, match: WindowMatch) -> bool:
        return self._show_window(match.hwnd, self.win32con.SW_MINIMIZE)

    def maximize_window(self, match: WindowMatch) -> bool:
        return self._show_window(match.hwnd, self.win32con.SW_MAXIMIZE)

    def restore_window(self, match: WindowMatch) -> bool:
        return self._show_window(match.hwnd, self.win32con.SW_RESTORE)

    def close_window(self, match: WindowMatch) -> bool:
        if not self.is_available():
            return False
        try:
            self.win32gui.PostMessage(match.hwnd, self.win32con.WM_CLOSE, 0, 0)
        except Exception:  # noqa: BLE001 - window may reject or disappear
            return False
        return True

    def find_by_hwnd(self, hwnd: int, *, require_visible: bool = True) -> WindowMatch | None:
        if not self.is_available():
            return None
        try:
            if not self.win32gui.IsWindow(hwnd):
                return None
            if require_visible and not self._is_visible_window(hwnd):
                return None
            return self._window_match(hwnd)
        except Exception:  # noqa: BLE001 - HWND may be stale
            return None

    def get_foreground_window(self) -> WindowMatch | None:
        if not self.is_available():
            return None
        try:
            hwnd = self.win32gui.GetForegroundWindow()
        except Exception:  # noqa: BLE001 - desktop may be unavailable
            return None
        return self.find_by_hwnd(int(hwnd))

    def find_by_title_keywords(self, keywords: Iterable[str]) -> WindowMatch | None:
        if not self.is_available():
            return None
        normalized_keywords = normalize_keywords(keywords)
        if not normalized_keywords:
            return None

        matches: list[WindowMatch] = []

        def callback(hwnd: int, _extra: object) -> bool:
            if not self._is_visible_window(hwnd):
                return True
            title = self.win32gui.GetWindowText(hwnd)
            title_norm = title.lower()
            if not any(keyword in title_norm for keyword in normalized_keywords):
                return True
            process_id = self.win32process.GetWindowThreadProcessId(hwnd)[1]
            matches.append(self._window_match(hwnd, title=title, process_id=process_id))
            return True

        self.win32gui.EnumWindows(callback, None)
        return matches[0] if matches else None

    def wait_for_executable(self, executable_path: str, timeout_seconds: float = 5.0) -> WindowMatch | None:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while time.monotonic() <= deadline:
            match = self.find_by_executable(executable_path)
            if match is not None:
                return match
            time.sleep(0.2)
        return None

    def wait_for_title_keywords(self, keywords: Iterable[str], timeout_seconds: float = 5.0) -> WindowMatch | None:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while time.monotonic() <= deadline:
            match = self.find_by_title_keywords(keywords)
            if match is not None:
                return match
            time.sleep(0.2)
        return None

    def find_process_by_executable(self, executable_path: str) -> ProcessMatch | None:
        if not self.is_available():
            return None
        target = normalize_path(executable_path)
        if not target:
            return None
        for process in self._process_matches():
            if normalize_path(process.executable_path) == target:
                return process
        return None

    def find_process_by_keywords(self, keywords: Iterable[str]) -> ProcessMatch | None:
        if not self.is_available():
            return None
        normalized_keywords = normalize_keywords(keywords)
        if not normalized_keywords:
            return None
        for process in self._process_matches():
            process_path = process.executable_path.lower()
            if any(keyword in process_path for keyword in normalized_keywords):
                return process
        return None

    def _is_visible_window(self, hwnd: int) -> bool:
        if not self.win32gui.IsWindowVisible(hwnd):
            return False
        title = self.win32gui.GetWindowText(hwnd)
        return bool(title.strip())

    def _show_window(self, hwnd: int, command: int) -> bool:
        if not self.is_available():
            return False
        try:
            self.win32gui.ShowWindow(hwnd, command)
        except Exception:  # noqa: BLE001 - stale handles and access issues are expected
            return False
        return True

    def _window_match(
        self,
        hwnd: int,
        *,
        title: str | None = None,
        process_id: int | None = None,
    ) -> WindowMatch:
        actual_process_id = process_id
        if actual_process_id is None:
            actual_process_id = self.win32process.GetWindowThreadProcessId(hwnd)[1]
        return WindowMatch(
            hwnd=hwnd,
            title=title if title is not None else self.win32gui.GetWindowText(hwnd),
            process_id=actual_process_id,
            executable_path=self._process_executable(actual_process_id),
            is_minimized=bool(self.win32gui.IsIconic(hwnd)),
            is_maximized=self._is_maximized(hwnd),
        )

    def _is_maximized(self, hwnd: int) -> bool:
        try:
            return bool(self.win32gui.IsZoomed(hwnd))
        except Exception:  # noqa: BLE001 - optional Win32 state
            return False

    def _process_executable(self, process_id: int) -> str:
        handle = None
        try:
            access = self.win32con.PROCESS_QUERY_INFORMATION | self.win32con.PROCESS_VM_READ
            handle = self.win32api.OpenProcess(access, False, process_id)
            return str(self.win32process.GetModuleFileNameEx(handle, 0))
        except Exception:  # noqa: BLE001 - process may have exited or deny access
            return ""
        finally:
            if handle is not None:
                try:
                    self.win32api.CloseHandle(handle)
                except Exception:  # noqa: BLE001 - best effort cleanup
                    pass

    def _process_matches(self) -> list[ProcessMatch]:
        try:
            process_ids = self.win32process.EnumProcesses()
        except Exception:  # noqa: BLE001 - process enumeration is best-effort
            return []

        matches: list[ProcessMatch] = []
        for process_id in process_ids:
            executable_path = self._process_executable(int(process_id))
            if executable_path:
                matches.append(ProcessMatch(process_id=int(process_id), executable_path=executable_path))
        return matches
