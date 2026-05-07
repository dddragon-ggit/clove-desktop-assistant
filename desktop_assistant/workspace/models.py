from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from ..models import ActionPlan


class WorkspaceResource(BaseModel):
    kind: str
    target: str
    title: str = ""
    reason: str = ""
    action_type: str


class WorkspaceSuggestion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str
    title: str
    summary: str = ""
    resources: list[WorkspaceResource] = Field(default_factory=list)
    plan: ActionPlan
    source: str = "workspace_builder"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    user_feedback: list[str] = Field(default_factory=list)

    def has_actions(self) -> bool:
        return bool(self.plan.steps)
