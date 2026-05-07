from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from ..storage import quarantine_corrupted_file, write_json_atomic
from .models import ACTIVITY_LOG_SCHEMA_VERSION, ActivitySnapshot


def default_activity_log_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "activity_log.json"


class ActivityStore:
    """Persist metadata-only desktop activity snapshots."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_activity_log_path()

    def load(self) -> list[ActivitySnapshot]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            quarantine_corrupted_file(self.path, source="activity_store", category="activity_store_corrupted", reason="Activity log JSON is unreadable.")
            return []
        if not isinstance(payload, dict):
            quarantine_corrupted_file(self.path, source="activity_store", category="activity_store_invalid", reason="Activity log root must be an object.")
            return []
        raw_records = payload.get("records") or []
        if not isinstance(raw_records, list):
            quarantine_corrupted_file(self.path, source="activity_store", category="activity_store_invalid", reason="Activity log records must be a list.")
            return []
        try:
            return [
                ActivitySnapshot.model_validate(item)
                for item in raw_records
                if isinstance(item, dict)
            ]
        except Exception:
            quarantine_corrupted_file(self.path, source="activity_store", category="activity_store_invalid", reason="Activity snapshots could not be validated.")
            return []

    def save(self, records: Iterable[ActivitySnapshot]) -> None:
        payload = {
            "schema_version": ACTIVITY_LOG_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "records": [record.model_dump(mode="json") for record in records],
        }
        write_json_atomic(self.path, payload)

    def append(self, snapshot: ActivitySnapshot, *, max_records: int = 500) -> ActivitySnapshot:
        records = self.load()
        if records and records[-1].activity_signature() == snapshot.activity_signature():
            records[-1] = snapshot
        else:
            records.append(snapshot)
        self.save(records[-max(1, int(max_records)) :])
        return snapshot

    def recent(self, limit: int = 20) -> list[ActivitySnapshot]:
        if limit <= 0:
            return []
        records = self.load()
        return list(reversed(records[-int(limit) :]))
