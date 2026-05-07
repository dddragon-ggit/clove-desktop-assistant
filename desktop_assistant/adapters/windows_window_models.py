from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WindowMatch:
    hwnd: int
    title: str
    process_id: int
    executable_path: str = ""
    is_minimized: bool = False
    is_maximized: bool = False


@dataclass(frozen=True)
class ProcessMatch:
    process_id: int
    executable_path: str


class WindowManagerProtocol(Protocol):
    def is_available(self) -> bool:
        """Return whether real window inspection is available."""

    def find_by_executable(self, executable_path: str) -> WindowMatch | None:
        """Find the first visible top-level window for an executable."""

    def focus_window(self, match: WindowMatch) -> bool:
        """Bring a matched window to foreground."""

    def minimize_window(self, match: WindowMatch) -> bool:
        """Minimize a matched window."""

    def maximize_window(self, match: WindowMatch) -> bool:
        """Maximize a matched window."""

    def restore_window(self, match: WindowMatch) -> bool:
        """Restore a minimized or maximized matched window."""

    def close_window(self, match: WindowMatch) -> bool:
        """Request a matched window to close."""

    def find_by_hwnd(self, hwnd: int, *, require_visible: bool = True) -> WindowMatch | None:
        """Find a top-level window by HWND. When require_visible is False, minimized windows are included."""

    def get_foreground_window(self) -> WindowMatch | None:
        """Return the current foreground window when available."""

    def wait_for_executable(self, executable_path: str, timeout_seconds: float = 5.0) -> WindowMatch | None:
        """Wait for a visible window belonging to the executable."""

    def find_by_title_keywords(self, keywords: Iterable[str]) -> WindowMatch | None:
        """Find the first visible top-level window whose title matches app keywords."""

    def wait_for_title_keywords(self, keywords: Iterable[str], timeout_seconds: float = 5.0) -> WindowMatch | None:
        """Wait for a visible window whose title matches app keywords."""

    def find_process_by_executable(self, executable_path: str) -> ProcessMatch | None:
        """Find a running process for an executable, even if it has no visible window."""

    def find_process_by_keywords(self, keywords: Iterable[str]) -> ProcessMatch | None:
        """Find a running process whose executable path matches app keywords."""

    def list_visible_windows(self, limit: int = 50) -> list[WindowMatch]:
        """List visible top-level windows."""
