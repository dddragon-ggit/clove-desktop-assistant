from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time

from .models import TodoItem, TodoStatus
from .reminder_settings import ReminderSettings, logical_local_date


DEFAULT_REPEAT_MINUTES = 30
MISSED_REMINDER_GRACE_MINUTES = 90
MAX_REPEAT_REMINDERS = 3
DEFAULT_QUIET_HOURS = (time(23, 0), time(7, 0))


@dataclass(frozen=True)
class DueTodoReminder:
    todo: TodoItem
    reminder_key: str
    kind: str = "due"


def due_todo_reminders(
    todos: list[TodoItem],
    *,
    now: datetime | None = None,
    repeat_minutes: int = DEFAULT_REPEAT_MINUTES,
    quiet_hours: tuple[time, time] | None = DEFAULT_QUIET_HOURS,
    max_repeat_reminders: int = MAX_REPEAT_REMINDERS,
    settings: ReminderSettings | None = None,
) -> list[DueTodoReminder]:
    current = _aware(now or datetime.now(UTC))
    if settings is not None:
        quiet_hours = settings.quiet_hours()
    if quiet_hours is not None and _is_quiet_time(current, quiet_hours):
        return []
    reminders: list[DueTodoReminder] = []
    for todo in todos:
        policy = settings.policy_for(todo) if settings is not None else None
        if policy is not None and not policy.enabled:
            continue
        effective_repeat_minutes = policy.repeat_minutes if policy is not None else repeat_minutes
        effective_max_repeats = (policy.max_repeats if policy is not None and policy.repeat_enabled else 0) if policy is not None else max_repeat_reminders
        base_due_at = _parse_time(todo.next_time())
        snoozed_until = _parse_time(todo.snoozed_until)
        effective_due_at = snoozed_until or base_due_at
        if todo.status != TodoStatus.OPEN or effective_due_at is None:
            continue
        if _is_daily_completed_or_skipped(todo, current, settings=settings):
            continue
        local_due_at = effective_due_at.astimezone(current.tzinfo)
        if todo.is_daily():
            today_due_at = datetime.combine(current.date(), local_due_at.time(), tzinfo=current.tzinfo)
            if today_due_at > current:
                continue
            local_due_at = max(today_due_at, local_due_at) if snoozed_until is not None else today_due_at
            reminder_key = _daily_reminder_key(todo, current, local_due_at, snoozed_until=snoozed_until)
            if todo.last_reminder_key == _legacy_daily_reminder_key(todo, current):
                continue
        else:
            if local_due_at > current:
                continue
            reminder_key = f"temporary:{todo.id}:{local_due_at.isoformat()}"
        kind = _reminder_kind(local_due_at, current, snoozed=snoozed_until is not None)
        if todo.last_reminder_key == reminder_key:
            repeat = _repeat_reminder(
                todo,
                current,
                repeat_minutes=effective_repeat_minutes,
                max_repeat_reminders=effective_max_repeats,
            )
            if repeat is None:
                continue
            reminders.append(repeat)
            continue
        reminders.append(DueTodoReminder(todo=todo, reminder_key=reminder_key, kind=kind))
    return reminders


def _is_daily_completed_or_skipped(todo: TodoItem, current: datetime, *, settings: ReminderSettings | None) -> bool:
    if not todo.is_daily():
        return False
    if settings is None:
        return todo.is_daily_completed_today(now=current) or todo.is_daily_skipped_today(now=current)
    today = logical_local_date(current, daily_reset_hour=settings.daily_reset_hour)
    return todo.daily_completed_on == today or todo.daily_skipped_on == today


def _daily_reminder_key(todo: TodoItem, current: datetime, due_at: datetime, *, snoozed_until: datetime | None) -> str:
    if snoozed_until is not None:
        return f"daily-snooze:{todo.id}:{snoozed_until.isoformat()}"
    return f"daily:{todo.id}:{current.date().isoformat()}:{due_at.time().isoformat(timespec='minutes')}"


def _legacy_daily_reminder_key(todo: TodoItem, current: datetime) -> str:
    return f"daily:{todo.id}:{current.date().isoformat()}"


def _reminder_kind(due_at: datetime, current: datetime, *, snoozed: bool) -> str:
    if snoozed:
        return "snoozed"
    late_minutes = int((current - due_at).total_seconds() // 60)
    if late_minutes >= MISSED_REMINDER_GRACE_MINUTES:
        return "missed"
    return "due"


def _repeat_reminder(
    todo: TodoItem,
    current: datetime,
    *,
    repeat_minutes: int,
    max_repeat_reminders: int,
) -> DueTodoReminder | None:
    if not todo.last_reminded_at or todo.reminder_repeat_count >= max_repeat_reminders:
        return None
    last_reminded_at = _parse_time(todo.last_reminded_at)
    if last_reminded_at is None:
        return None
    elapsed_minutes = int((current - last_reminded_at.astimezone(current.tzinfo)).total_seconds() // 60)
    if elapsed_minutes < max(1, repeat_minutes):
        return None
    base_key = todo.last_reminder_key or f"repeat:{todo.id}"
    return DueTodoReminder(
        todo=todo,
        reminder_key=f"{base_key}:repeat:{todo.reminder_repeat_count + 1}",
        kind="repeat",
    )


def _is_quiet_time(current: datetime, quiet_hours: tuple[time, time]) -> bool:
    start, end = quiet_hours
    current_time = current.astimezone().time()
    if start <= end:
        return start <= current_time < end
    return current_time >= start or current_time < end


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
