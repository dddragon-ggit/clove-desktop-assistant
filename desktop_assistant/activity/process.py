from __future__ import annotations

from typing import Protocol


class ProcessMetadataProviderProtocol(Protocol):
    def get_command_line(self, process_id: int) -> str:
        """Return the process command line when available."""


class WindowsProcessMetadataProvider:
    """Best-effort WMI reader for process command lines.

    This reads process metadata only. It does not inspect window contents, keystrokes, or files.
    """

    def get_command_line(self, process_id: int) -> str:
        if process_id <= 0:
            return ""
        try:
            import win32com.client  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001 - optional Windows integration
            return ""

        try:
            service = win32com.client.GetObject("winmgmts:")
            query = f"SELECT CommandLine FROM Win32_Process WHERE ProcessId = {int(process_id)}"
            for process in service.ExecQuery(query):
                return str(getattr(process, "CommandLine", "") or "")
        except Exception:  # noqa: BLE001 - process may deny metadata access
            return ""
        return ""


class NullProcessMetadataProvider:
    def get_command_line(self, process_id: int) -> str:
        return ""
