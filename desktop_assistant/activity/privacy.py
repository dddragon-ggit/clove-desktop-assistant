from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from ..storage import quarantine_corrupted_file, write_json_atomic
from .models import ActivitySnapshot
from .store import ActivityStore


ACTIVITY_PRIVACY_SCHEMA_VERSION = 1


class ActivityPrivacySettings(BaseModel):
    enabled: bool = True
    excluded_apps: list[str] = Field(default_factory=list)
    save_file_paths: bool = True

    def excludes_app(self, app_name: str) -> bool:
        lowered = app_name.strip().lower()
        return bool(lowered) and any(item.strip().lower() in lowered for item in self.excluded_apps)


def default_activity_privacy_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "activity_privacy.json"


class ActivityPrivacyStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_activity_privacy_path()

    def load(self) -> ActivityPrivacySettings:
        if not self.path.exists():
            return ActivityPrivacySettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            quarantine_corrupted_file(self.path, source="activity_privacy_store", category="activity_privacy_corrupted", reason="Activity privacy JSON is unreadable.")
            return ActivityPrivacySettings()
        settings = payload.get("settings") if isinstance(payload, dict) else payload
        if not isinstance(settings, dict):
            quarantine_corrupted_file(self.path, source="activity_privacy_store", category="activity_privacy_invalid", reason="Activity privacy payload is invalid.")
            return ActivityPrivacySettings()
        try:
            return ActivityPrivacySettings.model_validate(settings)
        except Exception:
            quarantine_corrupted_file(self.path, source="activity_privacy_store", category="activity_privacy_invalid", reason="Activity privacy settings could not be validated.")
            return ActivityPrivacySettings()

    def save(self, settings: ActivityPrivacySettings) -> ActivityPrivacySettings:
        payload = {
            "schema_version": ACTIVITY_PRIVACY_SCHEMA_VERSION,
            "settings": settings.model_dump(mode="json"),
        }
        write_json_atomic(self.path, payload)
        return settings


def apply_activity_privacy(
    snapshot: ActivitySnapshot,
    settings: ActivityPrivacySettings,
) -> ActivitySnapshot | None:
    if not settings.enabled:
        return None
    if snapshot.active_app and settings.excludes_app(snapshot.active_app.name):
        return None
    if settings.save_file_paths:
        return snapshot
    redacted = snapshot.model_copy(deep=True)
    if redacted.active_file:
        redacted.active_file.path = ""
    for recent in redacted.recent_files:
        recent.path = ""
    return redacted


def clear_activity_records(
    *,
    activity_store: ActivityStore | None = None,
    activity_days_dir: str | Path | None = None,
) -> None:
    store = activity_store or ActivityStore()
    store.save([])
    days_dir = Path(activity_days_dir) if activity_days_dir is not None else Path.cwd() / "runtime" / "data" / "activity_days"
    if days_dir.exists():
        for path in days_dir.glob("*.md"):
            path.unlink(missing_ok=True)
