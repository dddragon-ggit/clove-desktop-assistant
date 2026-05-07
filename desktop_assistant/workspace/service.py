from __future__ import annotations

from uuid import NAMESPACE_DNS, uuid5

from ..models import ActionStep, RiskLevel
from ..recipe import RecipeStore, WorkflowRecipe
from .builder import WorkspaceSuggestionBuilder
from .drafts import WorkspaceDraftStore
from .models import WorkspaceResource, WorkspaceSuggestion


class WorkspaceService:
    """Product-level helpers around workspace suggestions."""

    def __init__(
        self,
        *,
        builder: WorkspaceSuggestionBuilder | None = None,
        recipe_store: RecipeStore | None = None,
        draft_store: WorkspaceDraftStore | None = None,
    ) -> None:
        self.builder = builder or WorkspaceSuggestionBuilder()
        self.recipe_store = recipe_store or RecipeStore()
        self.draft_store = draft_store or WorkspaceDraftStore()

    def refine(self, suggestion: WorkspaceSuggestion, user_feedback: str) -> WorkspaceSuggestion:
        refined = self.builder.refine(suggestion, user_feedback)
        self.draft_store.upsert(refined, status="pending")
        return refined

    def save_draft(self, suggestion: WorkspaceSuggestion) -> WorkspaceSuggestion:
        self.draft_store.upsert(suggestion, status="pending")
        return suggestion

    def save_as_recipe(
        self,
        suggestion: WorkspaceSuggestion,
        *,
        name: str | None = None,
        risk_level: RiskLevel = RiskLevel.LOW,
    ) -> WorkflowRecipe:
        recipe = self.recipe_store.create_from_steps(
            name=name or suggestion.title,
            user_goal=suggestion.goal,
            plan_name=suggestion.plan.plan_name,
            risk_level=risk_level,
            steps=suggestion.plan.steps,
            description=suggestion.summary,
            scenario="workspace",
            user_refinement="; ".join(suggestion.user_feedback),
            revision_note="Saved workspace suggestion as recipe.",
        )
        self.draft_store.mark_status(suggestion.id, "saved")
        return recipe

    def list_recipes(self) -> list[WorkflowRecipe]:
        recipes = [recipe for recipe in self.recipe_store.load() if recipe.scenario == "workspace"]
        return sorted(recipes, key=lambda recipe: recipe.updated_at, reverse=True)

    def find_workspace_recipe(self, goal: str) -> WorkflowRecipe | None:
        recipe = self.recipe_store.find(goal)
        if recipe is None or recipe.scenario != "workspace":
            return None
        return recipe

    def recipe_for_goal(self, goal: str) -> WorkspaceSuggestion | None:
        recipe = self.find_workspace_recipe(goal)
        if recipe is None:
            return None
        return self.recipe_as_suggestion(recipe.id)

    def pending_draft(self, suggestion_id: str | None) -> WorkspaceSuggestion | None:
        return self.draft_store.get_pending(suggestion_id)

    def recipe_as_suggestion(self, recipe_id: str) -> WorkspaceSuggestion | None:
        recipe = self.recipe_store.get(recipe_id)
        if recipe is None or recipe.scenario != "workspace":
            return None
        suggestion_id = str(uuid5(NAMESPACE_DNS, f"workspace-recipe:{recipe_id}"))
        suggestion = WorkspaceSuggestion(
            id=suggestion_id,
            goal=recipe.user_goal,
            title=recipe.name,
            summary=recipe.description or f"已加载 {len(recipe.plan.steps)} 个工作区动作。",
            resources=[_resource_from_step(step) for step in recipe.plan.steps],
            plan=recipe.plan.model_copy(deep=True),
            source="workspace_recipe",
        )
        return self.save_draft(suggestion)


def _resource_from_step(step: ActionStep) -> WorkspaceResource:
    return WorkspaceResource(
        kind=_resource_kind(step.action_type.value),
        target=step.target,
        title=step.target,
        reason=step.reason,
        action_type=step.action_type.value,
    )


def _resource_kind(action_type: str) -> str:
    return {
        "open_app": "app",
        "focus_app": "app",
        "open_url": "url",
        "open_file": "file",
        "open_folder": "folder",
        "open_project": "project",
    }.get(action_type, "other")
