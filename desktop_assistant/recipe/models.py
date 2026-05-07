from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from ..models import ActionPlan, RiskLevel

RECIPE_SCHEMA_VERSION = 2


class RecipeRevision(BaseModel):
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_trace_id: str | None = None
    user_refinement: str = ""
    plan_name: str = ""
    action_count: int = 0
    note: str = ""


class RecipeCheckIssue(BaseModel):
    severity: str
    code: str
    message: str
    step_index: int | None = None


class RecipeCheckResult(BaseModel):
    checked_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    ok: bool
    issues: list[RecipeCheckIssue] = Field(default_factory=list)


class WorkflowRecipe(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    user_goal: str
    description: str = ""
    scenario: str = ""
    plan: ActionPlan
    risk_level: RiskLevel
    revision_history: list[RecipeRevision] = Field(default_factory=list)
    last_check: RecipeCheckResult | None = None
    last_run_status: str | None = None
    last_run_message: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
