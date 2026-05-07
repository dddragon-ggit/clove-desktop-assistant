from __future__ import annotations

from collections.abc import Iterable

from .windows_window_models import ProcessMatch, WindowMatch


class NullWindowManager:
    def is_available(self) -> bool:
        return False

    def find_by_executable(self, executable_path: str) -> WindowMatch | None:
        return None

    def focus_window(self, match: WindowMatch) -> bool:
        return False

    def minimize_window(self, match: WindowMatch) -> bool:
        return False

    def maximize_window(self, match: WindowMatch) -> bool:
        return False

    def restore_window(self, match: WindowMatch) -> bool:
        return False

    def close_window(self, match: WindowMatch) -> bool:
        return False

    def find_by_hwnd(self, hwnd: int, *, require_visible: bool = True) -> WindowMatch | None:
        return None

    def get_foreground_window(self) -> WindowMatch | None:
        return None

    def wait_for_executable(self, executable_path: str, timeout_seconds: float = 5.0) -> WindowMatch | None:
        return None

    def find_by_title_keywords(self, keywords: Iterable[str]) -> WindowMatch | None:
        return None

    def wait_for_title_keywords(self, keywords: Iterable[str], timeout_seconds: float = 5.0) -> WindowMatch | None:
        return None

    def find_process_by_executable(self, executable_path: str) -> ProcessMatch | None:
        return None

    def find_process_by_keywords(self, keywords: Iterable[str]) -> ProcessMatch | None:
        return None

    def list_visible_windows(self, limit: int = 50) -> list[WindowMatch]:
        return []
