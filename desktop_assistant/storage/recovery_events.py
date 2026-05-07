from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from .json_files import write_json_atomic


RECOVERY_EVENT_SCHEMA_VERSION = 1


def default_recovery_event_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "recovery_events.json"


class RecoveryEventRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source: str
    category: str
    path: str
    quarantined_path: str
    reason: str = ""


class RecoveryEventStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_recovery_event_path()

    def load(self) -> list[RecoveryEventRecord]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            from .json_files import quarantine_corrupted_file

            quarantine_corrupted_file(
                self.path,
                category="recovery_event_log_corrupted",
                source="recovery_event_store",
                reason="Recovery event log JSON is unreadable.",
                record_event=False,
            )
            return []
        if not isinstance(payload, dict):
            return []
        raw_records = payload.get("events") or []
        if not isinstance(raw_records, list):
            return []
        records: list[RecoveryEventRecord] = []
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            try:
                records.append(RecoveryEventRecord.model_validate(item))
            except Exception:
                continue
        return records

    def save(self, records: list[RecoveryEventRecord]) -> None:
        payload = {
            "schema_version": RECOVERY_EVENT_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "events": [record.model_dump(mode="json") for record in records],
        }
        write_json_atomic(self.path, payload)

    def append(
        self,
        *,
        source: str,
        category: str,
        path: str | Path,
        quarantined_path: str | Path,
        reason: str = "",
        max_records: int = 200,
    ) -> RecoveryEventRecord:
        records = self.load()
        record = RecoveryEventRecord(
            source=source,
            category=category,
            path=str(path),
            quarantined_path=str(quarantined_path),
            reason=reason,
        )
        records.append(record)
        self.save(records[-max(1, int(max_records)) :])
        return record

    def latest(self, *, max_age_hours: int = 24) -> RecoveryEventRecord | None:
        records = self.load()
        if not records:
            return None
        latest = max(records, key=lambda item: item.created_at)
        try:
            created_at = datetime.fromisoformat(latest.created_at.replace("Z", "+00:00"))
        except ValueError:
            return latest
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if created_at < datetime.now(UTC) - timedelta(hours=max_age_hours):
            return None
        return latest


def record_recovery_event(
    *,
    source: str,
    category: str,
    path: str | Path,
    quarantined_path: str | Path,
    reason: str = "",
) -> RecoveryEventRecord:
    return RecoveryEventStore().append(
        source=source,
        category=category,
        path=path,
        quarantined_path=quarantined_path,
        reason=reason,
    )


def recovery_notice_text(record: RecoveryEventRecord | None) -> str:
    if record is None:
        return ""
    source_label = {
        "todo_store": "待办数据",
        "workspace_draft_store": "工作区草稿",
        "recipe_store": "工作区方案",
        "prediction_store": "预测建议",
        "project_catalog_store": "项目目录",
        "activity_store": "活动记录",
        "activity_privacy_store": "隐私设置",
        "ui_state_store": "界面状态",
        "provider_config_store": "模型配置",
        "action_trust_store": "信任白名单",
        "capability_store": "能力目录",
        "app_inventory_store": "应用清单",
        "recovery_event_store": "恢复日志",
    }.get(record.source, "本地数据")
    quarantined_name = Path(record.quarantined_path).name
    return f"检测到{source_label}异常，已自动隔离旧文件：{quarantined_name}"
