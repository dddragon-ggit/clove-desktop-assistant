from __future__ import annotations

from datetime import UTC, datetime

from .models import TodoHomeStatus, TodoItem, TodoStatus, TodoUrgency


URGENCY_COLORS = {
    TodoUrgency.RED: "#C2413B",
    TodoUrgency.ORANGE: "#D97706",
    TodoUrgency.YELLOW: "#C99A1A",
    TodoUrgency.GREEN: "#2E7D5B",
}


def build_home_status(items: list[TodoItem], *, now: datetime | None = None) -> TodoHomeStatus:
    current = _aware(now or datetime.now(UTC))
    open_items = [item for item in items if item.status == TodoStatus.OPEN and not item.is_daily_completed_today(now=current)]
    important_open_count = sum(1 for item in open_items if item.is_important())
    next_item, minutes_until_next = _next_timed_item(open_items, current)
    urgency = _urgency(open_items, minutes_until_next)
    return TodoHomeStatus(
        greeting=greeting_for_time(current),
        urgency=urgency,
        color=URGENCY_COLORS[urgency],
        important_open_count=important_open_count,
        open_count=len(open_items),
        next_task_id=next_item.id if next_item else None,
        next_task_title=next_item.title if next_item else None,
        next_task_time=next_item.next_time() if next_item else None,
        minutes_until_next=minutes_until_next,
    )


def greeting_for_time(now: datetime | None = None) -> str:
    current = _aware(now or datetime.now(UTC))
    hour = current.astimezone().hour
    if 5 <= hour < 12:
        return "早上好"
    if 12 <= hour < 18:
        return "下午好"
    return "晚上好"


def _urgency(open_items: list[TodoItem], minutes_until_next: int | None) -> TodoUrgency:
    if not open_items:
        return TodoUrgency.GREEN
    if minutes_until_next is None:
        return TodoUrgency.YELLOW
    if minutes_until_next <= 30:
        return TodoUrgency.RED
    if minutes_until_next <= 180:
        return TodoUrgency.ORANGE
    return TodoUrgency.YELLOW


def _next_timed_item(items: list[TodoItem], now: datetime) -> tuple[TodoItem | None, int | None]:
    candidates: list[tuple[datetime, TodoItem]] = []
    for item in items:
        timestamp = _parse_time(item.next_time())
        if timestamp is not None:
            candidates.append((timestamp, item))
    if not candidates:
        return None, None
    target_time, target_item = min(candidates, key=lambda pair: pair[0])
    minutes = int((target_time - now).total_seconds() // 60)
    return target_item, max(0, minutes)


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
