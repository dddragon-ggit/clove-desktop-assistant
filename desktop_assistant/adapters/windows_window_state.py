from __future__ import annotations

from .windows_window_manager import WindowsWindowManager
from .windows_window_models import ProcessMatch, WindowManagerProtocol, WindowMatch
from .windows_window_null import NullWindowManager
from .windows_window_utils import (
    _normalize_keywords,
    _normalize_path,
    normalize_keywords,
    normalize_path,
)

__all__ = [
    "NullWindowManager",
    "ProcessMatch",
    "WindowManagerProtocol",
    "WindowMatch",
    "WindowsWindowManager",
    "normalize_keywords",
    "normalize_path",
    "_normalize_keywords",
    "_normalize_path",
]
