from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtGui import QColor

from ..todo import TodoItem


def todo_item_color(item: TodoItem, *, now: datetime | None = None) -> QColor:
    current = _aware(now or datetime.now(UTC))
    minutes = _minutes_until(item.next_time(), current)
    if item.priority.value == "urgent" or (minutes is not None and minutes <= 30):
        return QColor(194, 65, 59, 150)
    if item.priority.value == "high" or item.important or (minutes is not None and minutes <= 180):
        return QColor(217, 119, 6, 135)
    if item.priority.value == "low":
        return QColor(46, 125, 91, 115)
    return QColor(201, 154, 26, 128)


def _minutes_until(value: str | None, now: datetime) -> int | None:
    if not value:
        return None
    try:
        target = _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None
    return max(0, int((target - now).total_seconds() // 60))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
