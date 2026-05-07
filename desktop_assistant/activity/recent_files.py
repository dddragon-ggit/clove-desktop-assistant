from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from .models import ActivityFile


class RecentFileProviderProtocol(Protocol):
    def list_recent_files(self, limit: int = 20) -> list[ActivityFile]:
        """Return recent document metadata without reading file contents."""


class WindowsRecentFileProvider:
    """Read Windows Recent Items shortcuts as a metadata-only signal."""

    def __init__(self, recent_dir: str | Path | None = None) -> None:
        self.recent_dir = Path(recent_dir) if recent_dir is not None else _default_recent_dir()

    def list_recent_files(self, limit: int = 20) -> list[ActivityFile]:
        if not self.recent_dir.exists() or not self.recent_dir.is_dir():
            return []
        safe_limit = max(1, min(int(limit), 100))
        try:
            shortcuts = sorted(
                self.recent_dir.glob("*.lnk"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return []

        records: list[ActivityFile] = []
        for shortcut in shortcuts[:safe_limit]:
            target = _shortcut_target(shortcut)
            if target:
                target_path = Path(target)
                records.append(
                    ActivityFile(
                        name=target_path.name,
                        path=str(target_path),
                        source="windows_recent",
                        confidence="medium",
                    )
                )
            else:
                records.append(
                    ActivityFile(
                        name=shortcut.stem,
                        path="",
                        source="windows_recent_shortcut",
                        confidence="low",
                    )
                )
        return records


class StaticRecentFileProvider:
    def __init__(self, files: list[ActivityFile] | None = None) -> None:
        self.files = files or []

    def list_recent_files(self, limit: int = 20) -> list[ActivityFile]:
        return self.files[: max(0, int(limit))]


def _default_recent_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Recent"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Recent"


def _shortcut_target(shortcut: Path) -> str:
    try:
        import win32com.client  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - pywin32 may not be present in tests
        return ""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        return str(shell.CreateShortcut(str(shortcut)).Targetpath or "")
    except Exception:  # noqa: BLE001 - corrupt or inaccessible shortcuts are ignored
        return ""
