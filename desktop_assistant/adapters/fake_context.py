from __future__ import annotations

from datetime import datetime

from ..models import ContextSnapshot


class FakeContextProvider:
    """Static context provider for deterministic tests."""

    def get_context(self) -> ContextSnapshot:
        now = datetime(2026, 4, 26, 19, 0, 0)
        return ContextSnapshot(
            local_time=now.isoformat(),
            date_label="2026-04-26",
            weekday="Sunday",
            timezone="Asia/Shanghai",
            weather="rainy",
            holiday=False,
        )
