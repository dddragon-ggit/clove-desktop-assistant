from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


UI_STATE_SCHEMA_VERSION = 1


class AssistantShellMode(str, Enum):
    PANEL = "panel"
    ORB = "orb"


class RectState(BaseModel):
    x: int = 0
    y: int = 0
    width: int = 360
    height: int = 240


class PointState(BaseModel):
    x: int = 0
    y: int = 0


class AssistantUiState(BaseModel):
    mode: AssistantShellMode = AssistantShellMode.PANEL
    panel: RectState = Field(default_factory=RectState)
    orb: PointState = Field(default_factory=PointState)
    orb_hidden: bool = False
    opacity: float = 1.0
    blur_enabled: bool = True
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
