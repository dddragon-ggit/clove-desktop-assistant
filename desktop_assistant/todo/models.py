from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


TODO_SCHEMA_VERSION = 1


class TodoStatus(str, Enum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class TodoPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TodoTaskType(str, Enum):
    DAILY = "daily"
    TEMPORARY = "temporary"


class TodoUrgency(str, Enum):
    RED = "red"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"


class TodoWorkspaceHint(BaseModel):
    apps: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    folders: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TodoExecutionRecord(BaseModel):
    trace_id: str = ""
    status: str = ""
    message: str = ""
    executed_actions: list[dict[str, str]] = Field(default_factory=list)
    ran_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class TodoItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str = ""
    status: TodoStatus = TodoStatus.OPEN
    priority: TodoPriority = TodoPriority.NORMAL
    task_type: TodoTaskType = TodoTaskType.TEMPORARY
    important: bool = False
    needs_computer: bool = False
    due_at: str | None = None
    reminder_at: str | None = None
    snoozed_until: str | None = None
    last_reminder_key: str | None = None
    last_reminded_at: str | None = None
    reminder_repeat_count: int = 0
    daily_completed_on: str | None = None
    daily_skipped_on: str | None = None
    workspace: TodoWorkspaceHint = Field(default_factory=TodoWorkspaceHint)
    workspace_confirmed: bool = False
    workspace_confirmed_at: str | None = None
    trusted_action_keys: list[str] = Field(default_factory=list)
    last_execution: TodoExecutionRecord | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None

    def is_open(self) -> bool:
        return self.status == TodoStatus.OPEN

    def is_important(self) -> bool:
        return self.important or self.priority in {TodoPriority.HIGH, TodoPriority.URGENT}

    def is_daily(self) -> bool:
        return self.task_type == TodoTaskType.DAILY

    def is_daily_completed_today(self, *, now: datetime | None = None, daily_reset_hour: int = 4) -> bool:
        if not self.is_daily() or not self.daily_completed_on:
            return False
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        from .reminder_settings import logical_local_date
        return self.daily_completed_on == logical_local_date(current, daily_reset_hour=daily_reset_hour)

    def is_daily_skipped_today(self, *, now: datetime | None = None, daily_reset_hour: int = 4) -> bool:
        if not self.is_daily() or not self.daily_skipped_on:
            return False
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        from .reminder_settings import logical_local_date
        return self.daily_skipped_on == logical_local_date(current, daily_reset_hour=daily_reset_hour)

    def next_time(self) -> str | None:
        return self.reminder_at or self.due_at


class TodoHomeStatus(BaseModel):
    greeting: str
    urgency: TodoUrgency
    color: str
    important_open_count: int
    open_count: int
    next_task_id: str | None = None
    next_task_title: str | None = None
    next_task_time: str | None = None
    minutes_until_next: int | None = None
