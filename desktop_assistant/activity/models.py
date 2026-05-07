from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


ACTIVITY_LOG_SCHEMA_VERSION = 1


class ActivityWindow(BaseModel):
    hwnd: int | None = None
    title: str = ""
    process_id: int | None = None
    executable_path: str = ""
    is_minimized: bool = False
    is_maximized: bool = False


class ActivityApp(BaseModel):
    name: str
    executable_path: str = ""
    process_id: int | None = None
    source: str = ""
    confidence: str = "unknown"


class ActivityFile(BaseModel):
    name: str
    path: str = ""
    source: str = ""
    confidence: str = "unknown"


class ActivityProject(BaseModel):
    name: str
    path: str
    kind: str = "project"
    source: str = ""
    confidence: str = "unknown"


class ActivitySnapshot(BaseModel):
    captured_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    active_window: ActivityWindow | None = None
    active_app: ActivityApp | None = None
    active_file: ActivityFile | None = None
    active_project: ActivityProject | None = None
    recent_files: list[ActivityFile] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    privacy_scope: str = "app/window/file/project metadata only; no keystrokes, screenshots, or document content"

    def activity_signature(self) -> str:
        parts = [
            self.active_app.name if self.active_app else "",
            self.active_file.path or self.active_file.name if self.active_file else "",
            self.active_project.path if self.active_project else "",
            self.active_window.title if self.active_window else "",
        ]
        return "|".join(part.strip().lower() for part in parts)
