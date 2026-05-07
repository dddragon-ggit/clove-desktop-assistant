from __future__ import annotations

from ..models import ActionPlan, PlanRefinementContext
from .utils import extract_refinement_constraints


def build_plan_refinement_context(
    *,
    original_goal: str,
    current_plan: ActionPlan,
    user_refinement: str,
    recipe_id: str | None = None,
    revision_index: int = 1,
) -> PlanRefinementContext:
    return PlanRefinementContext(
        original_goal=original_goal,
        current_plan=current_plan.model_copy(deep=True),
        user_refinement=user_refinement,
        constraints=extract_refinement_constraints(user_refinement),
        revision_index=max(1, revision_index),
        recipe_id=recipe_id,
    )
