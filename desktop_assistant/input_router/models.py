from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class InputRouteType(str, Enum):
    TODO = "todo"
    WORKSPACE = "workspace"
    CONTINUE_WORK = "continue_work"
    DIALOG = "dialog"


class InputRoute(BaseModel):
    route_type: InputRouteType
    normalized_text: str
    confidence: str = "low"
    source: str = "heuristic"
    accepted_prediction: bool = False
    target_id: str | None = None
    reason: str = ""
