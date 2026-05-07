from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from ..storage import quarantine_corrupted_file, write_json_atomic
from .models import TodoItem, TodoPriority, TodoTaskType


REMINDER_SETTINGS_SCHEMA_VERSION = 1
DEFAULT_QUIET_START = "23:00"
DEFAULT_QUIET_END = "07:00"
DEFAULT_DAILY_RESET_HOUR = 4


class ReminderPolicy(BaseModel):
    enabled: bool = True
    repeat_enabled: bool = True
    repeat_minutes: int = Field(default=30, ge=1, le=1440)
    max_repeats: int = Field(default=3, ge=0, le=20)
    snooze_minutes: int = Field(default=30, ge=1, le=1440)


class ReminderSettings(BaseModel):
    quiet_enabled: bool = True
    quiet_start: str = DEFAULT_QUIET_START
    quiet_end: str = DEFAULT_QUIET_END
    daily_reset_hour: int = Field(default=DEFAULT_DAILY_RESET_HOUR, ge=0, le=23)
    policies: dict[str, ReminderPolicy] = Field(default_factory=dict)

    def model_post_init(self, __context: object) -> None:
        defaults = default_reminder_policies()
        merged = {**defaults, **self.policies}
        self.policies = {key: _coerce_policy(value) for key, value in merged.items()}

    def quiet_hours(self) -> tuple[time, time] | None:
        if not self.quiet_enabled:
            return None
        return (_parse_clock(self.quiet_start, DEFAULT_QUIET_START), _parse_clock(self.quiet_end, DEFAULT_QUIET_END))

    def policy_for(self, todo: TodoItem) -> ReminderPolicy:
        return self.policy_for_values(todo.task_type, todo.priority)

    def policy_for_values(self, task_type: TodoTaskType | str, priority: TodoPriority | str) -> ReminderPolicy:
        key = reminder_policy_key(task_type, priority)
        return self.policies.get(key) or default_reminder_policy(task_type, priority)

    def logical_date(self, value: datetime) -> str:
        return logical_local_date(value, daily_reset_hour=self.daily_reset_hour)


def default_reminder_settings_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd()
    return root / "runtime" / "data" / "reminder_settings.json"


class ReminderSettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_reminder_settings_path()

    def load(self) -> ReminderSettings:
        if not self.path.exists():
            return ReminderSettings()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            quarantine_corrupted_file(
                self.path,
                source="reminder_settings_store",
                category="reminder_settings_corrupt",
                reason=f"Reminder settings could not be read: {type(exc).__name__}",
            )
            return ReminderSettings()
        settings = payload.get("settings") if isinstance(payload, dict) else payload
        try:
            return ReminderSettings.model_validate(settings)
        except Exception as exc:  # noqa: BLE001 - invalid user settings should recover to safe defaults.
            quarantine_corrupted_file(
                self.path,
                source="reminder_settings_store",
                category="reminder_settings_invalid",
                reason=f"Reminder settings could not be validated: {type(exc).__name__}",
            )
            return ReminderSettings()

    def save(self, settings: ReminderSettings) -> ReminderSettings:
        normalized = ReminderSettings.model_validate(settings.model_dump(mode="json"))
        write_json_atomic(
            self.path,
            {
                "schema_version": REMINDER_SETTINGS_SCHEMA_VERSION,
                "settings": normalized.model_dump(mode="json"),
            },
        )
        return normalized


def reminder_policy_key(task_type: TodoTaskType | str, priority: TodoPriority | str) -> str:
    task_value = task_type.value if isinstance(task_type, TodoTaskType) else str(task_type)
    priority_value = priority.value if isinstance(priority, TodoPriority) else str(priority)
    return f"{task_value}:{priority_value}"


def default_reminder_policies() -> dict[str, ReminderPolicy]:
    return {
        reminder_policy_key(task_type, priority): default_reminder_policy(task_type, priority)
        for task_type in TodoTaskType
        for priority in TodoPriority
    }


def default_reminder_policy(task_type: TodoTaskType | str, priority: TodoPriority | str) -> ReminderPolicy:
    task = task_type if isinstance(task_type, TodoTaskType) else TodoTaskType(str(task_type))
    level = priority if isinstance(priority, TodoPriority) else TodoPriority(str(priority))
    if task == TodoTaskType.DAILY:
        defaults = {
            TodoPriority.LOW: ReminderPolicy(repeat_enabled=False, repeat_minutes=60, max_repeats=0, snooze_minutes=30),
            TodoPriority.NORMAL: ReminderPolicy(repeat_enabled=True, repeat_minutes=60, max_repeats=1, snooze_minutes=30),
            TodoPriority.HIGH: ReminderPolicy(repeat_enabled=True, repeat_minutes=30, max_repeats=2, snooze_minutes=30),
            TodoPriority.URGENT: ReminderPolicy(repeat_enabled=True, repeat_minutes=15, max_repeats=4, snooze_minutes=10),
        }
    else:
        defaults = {
            TodoPriority.LOW: ReminderPolicy(repeat_enabled=False, repeat_minutes=60, max_repeats=0, snooze_minutes=30),
            TodoPriority.NORMAL: ReminderPolicy(repeat_enabled=True, repeat_minutes=30, max_repeats=3, snooze_minutes=30),
            TodoPriority.HIGH: ReminderPolicy(repeat_enabled=True, repeat_minutes=20, max_repeats=4, snooze_minutes=20),
            TodoPriority.URGENT: ReminderPolicy(repeat_enabled=True, repeat_minutes=10, max_repeats=6, snooze_minutes=10),
        }
    return defaults[level]


def logical_local_date(value: datetime, *, daily_reset_hour: int = DEFAULT_DAILY_RESET_HOUR) -> str:
    current = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    local = current.astimezone()
    if local.hour < max(0, min(23, int(daily_reset_hour))):
        local = local - timedelta(days=1)
    return local.date().isoformat()


def _parse_clock(value: str, fallback: str) -> time:
    try:
        hour_text, minute_text = value.strip().split(":", 1)
        hour = max(0, min(23, int(hour_text)))
        minute = max(0, min(59, int(minute_text)))
        return time(hour, minute)
    except (AttributeError, ValueError):
        hour_text, minute_text = fallback.split(":", 1)
        return time(int(hour_text), int(minute_text))


def _coerce_policy(value: ReminderPolicy | dict[str, object]) -> ReminderPolicy:
    if isinstance(value, ReminderPolicy):
        return value
    return ReminderPolicy.model_validate(value)
