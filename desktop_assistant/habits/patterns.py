from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from ..activity import ActivitySnapshot
from .context import context_label, same_meaningful_context


@dataclass(frozen=True)
class HabitTimeMatch:
    label: str
    confidence: str
    count: int
    source: str = "habit_time"


class HabitPatternAnalyzer:
    """Find simple repeated app/project patterns near the current hour."""

    def predict_same_hour(
        self,
        *,
        records: list[ActivitySnapshot],
        now: datetime,
        current_snapshot: ActivitySnapshot | None = None,
    ) -> HabitTimeMatch | None:
        counts: Counter[str] = Counter()
        for record in records:
            if same_meaningful_context(record, current_snapshot):
                continue
            if _hour(record.captured_at) != now.hour:
                continue
            label = context_label(record)
            if label:
                counts[label] += 1
        if not counts:
            return None
        label, count = counts.most_common(1)[0]
        if count < 2:
            return None
        confidence = "high" if count >= 4 else "medium"
        return HabitTimeMatch(label=label, confidence=confidence, count=count)


def _hour(value: str) -> int | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).hour
    except ValueError:
        return None
