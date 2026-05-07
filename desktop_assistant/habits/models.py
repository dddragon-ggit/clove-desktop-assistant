from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


PREDICTION_SCHEMA_VERSION = 1


class NextActionPrediction(BaseModel):
    suggested_text: str
    route_hint: str = "dialog"
    confidence: str = "low"
    source: str = ""
    target_id: str | None = None
    target_label: str | None = None
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    reasons: list[str] = Field(default_factory=list)

    @classmethod
    def empty(cls) -> "NextActionPrediction":
        return cls(
            suggested_text="",
            route_hint="dialog",
            confidence="low",
            source="none",
            reasons=["No prediction is available yet."],
        )
