from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta


def parse_todo_time(value: str, *, now: datetime | None = None) -> str | None:
    text = value.strip()
    if not text:
        return None
    current = _local(now)
    relative = _parse_relative(text, current)
    if relative is not None:
        return relative.astimezone(UTC).isoformat()
    clock = _parse_clock(text, current)
    if clock is not None:
        return clock.astimezone(UTC).isoformat()
    absolute = _parse_absolute(text, current)
    if absolute is not None:
        return absolute.astimezone(UTC).isoformat()
    return None


def _parse_relative(text: str, now: datetime) -> datetime | None:
    match = re.fullmatch(r"(\d+)\s*(m|min|minute|minutes|分钟)", text, flags=re.IGNORECASE)
    if match:
        return now + timedelta(minutes=int(match.group(1)))
    match = re.fullmatch(r"(\d+)\s*(h|hr|hour|hours|小时)", text, flags=re.IGNORECASE)
    if match:
        return now + timedelta(hours=int(match.group(1)))
    return None


def _parse_clock(text: str, now: datetime) -> datetime | None:
    day_offset = 0
    normalized = text
    if normalized.startswith("明天"):
        day_offset = 1
        normalized = normalized.removeprefix("明天").strip()
    match = re.fullmatch(r"(\d{1,2})[:：](\d{2})", normalized)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    candidate = datetime.combine((now + timedelta(days=day_offset)).date(), time(hour, minute), tzinfo=now.tzinfo)
    if day_offset == 0 and candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _parse_absolute(text: str, now: datetime) -> datetime | None:
    normalized = text.replace("年", "-").replace("月", "-").replace("日", " ").strip()
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=now.tzinfo)
    return parsed


def _local(value: datetime | None) -> datetime:
    current = value or datetime.now().astimezone()
    if current.tzinfo is None:
        return current.astimezone()
    return current
