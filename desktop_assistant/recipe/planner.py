from __future__ import annotations

from ..models import ContextSnapshot, PlannerResult, WorkflowRequest
from .models import WorkflowRecipe


class RecipePlanner:
    """Planner adapter that replays a saved recipe as a confirmable plan."""

    def __init__(self, recipe: WorkflowRecipe) -> None:
        self.recipe = recipe

    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        return PlannerResult(
            intent_summary=f"Saved recipe: {self.recipe.name}",
            requires_clarification=False,
            action_plan=self.recipe.plan.model_copy(deep=True),
            risk_guess=self.recipe.risk_level,
            reasoning_summary=(
                f"Loaded saved recipe {self.recipe.id} at {context.local_time}; "
                "the plan still goes through policy and reviewer before execution."
            ),
        )
