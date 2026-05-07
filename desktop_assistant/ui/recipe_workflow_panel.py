from __future__ import annotations

from ..action_trust import ActionTrustStore
from ..adapters.fake import FakeContextProvider, FakeExecutor, FakeReviewer
from ..adapters.windows_executor import WindowsExecutor
from ..capability.store import CapabilityStore
from ..core.orchestrator import WorkflowOrchestrator
from ..core.policy import PolicyEngine
from ..models import RunMode, WorkflowRequest
from ..recipe import RecipePlanner, build_plan_refinement_context
from .display_text import recipe_detail_text
from .view_model import summarize_trace


class RecipeWorkflowMixin:
    def load_selected_recipe_plan(self) -> None:
        recipe = self._selected_recipe()
        if recipe is None:
            return
        try:
            capability_registry = CapabilityStore().ensure(
                available_handler_names=WindowsExecutor.available_handler_names()
            )
            trusted_action_keys = ActionTrustStore().trusted_keys()
            orchestrator = WorkflowOrchestrator(
                planner=RecipePlanner(recipe),
                reviewer=FakeReviewer(),
                executor=FakeExecutor(),
                context_provider=FakeContextProvider(),
                storage=self.storage,
                policy_engine=PolicyEngine(
                    capability_registry=capability_registry,
                    trusted_action_keys=trusted_action_keys,
                ),
            )
            trace = orchestrator.run(
                WorkflowRequest(
                    user_request=f"Run saved recipe: {recipe.name}",
                    task_title=recipe.name,
                    scene_name=recipe.id,
                    run_mode=RunMode.DRY_RUN,
                )
            )
        except Exception as exc:  # noqa: BLE001 - keep recipe load errors visible
            self.set_error(f"Failed to load recipe: {type(exc).__name__}: {exc}")
            return

        self.active_recipe_id = recipe.id
        self.active_draft_goal = recipe.user_goal
        self.active_draft_refinements = [
            revision.user_refinement for revision in recipe.revision_history if revision.user_refinement
        ]
        self.request_input.setText(recipe.user_goal)
        self.on_dry_run_finished(summarize_trace(trace))
        self.summary_label.setText(f"Loaded recipe {recipe.name}. Review it, then Run Once.")

    def edit_selected_recipe(self) -> None:
        recipe = self._selected_recipe()
        if recipe is None:
            return
        self.active_recipe_id = recipe.id
        self.active_draft_goal = recipe.user_goal
        self.active_draft_refinements = [
            revision.user_refinement for revision in recipe.revision_history if revision.user_refinement
        ]
        self.request_input.setText(recipe.user_goal)
        self.summary_label.setText(f"Editing recipe: {recipe.name}")
        self.debug_snapshot_text.setPlainText(
            recipe_detail_text(recipe)
            + "\n\nEdit the request input, click Refine, then Save Recipe to update this recipe."
        )

    def delete_selected_recipe(self) -> None:
        recipe = self._selected_recipe()
        if recipe is None:
            return
        deleted = self.recipe_store.delete(recipe.id)
        self.selected_recipe_id = None
        self.active_recipe_id = None if self.active_recipe_id == recipe.id else self.active_recipe_id
        self._refresh_recipe_list()
        self.summary_label.setText(
            f"Deleted recipe: {recipe.name}" if deleted else f"Recipe was not found: {recipe.name}"
        )
        self.recipe_action_table.setRowCount(0)
        self.debug_snapshot_text.setPlainText("Select a recipe, project, capability, or debug run to inspect details.")

    def save_current_recipe(self) -> None:
        if self.latest_summary is None:
            return
        try:
            trace = self.storage.get_trace(self.latest_summary.trace_id)
        except KeyError as exc:
            self.set_error(str(exc))
            return
        if not trace.planner_result.action_plan.steps:
            self.confirmation_label.setText("No actions to save as a recipe.")
            return

        existing_recipe = (
            self.recipe_store.get(self.active_recipe_id)
            if self.active_recipe_id
            else None
        )
        refinement = trace.request.plan_refinement
        user_goal = refinement.original_goal if refinement is not None else trace.request.user_request
        user_refinement = refinement.user_refinement if refinement is not None else ""
        recipe_name = (
            existing_recipe.name
            if existing_recipe is not None
            else trace.request.task_title or user_goal
        )
        recipe = self.recipe_store.create_from_steps(
            name=recipe_name,
            user_goal=user_goal,
            plan_name=trace.planner_result.action_plan.plan_name,
            risk_level=trace.policy_decision.risk_level,
            steps=trace.planner_result.action_plan.steps,
            recipe_id=self.active_recipe_id,
            description=existing_recipe.description if existing_recipe is not None else "",
            scenario=existing_recipe.scenario if existing_recipe is not None else trace.request.scene_name or "",
            previous_revision_history=(
                existing_recipe.revision_history if existing_recipe is not None else []
            ),
            source_trace_id=trace.trace_id,
            user_refinement=user_refinement,
            revision_note="Saved refined draft" if user_refinement else "Saved draft",
        )
        self.active_recipe_id = recipe.id
        self._refresh_recipe_list()
        self._select_recipe(recipe.id)
        self.status_badge.setText("Recipe")
        self.summary_label.setText(f"Saved recipe: {recipe.name}")
        self.confirmation_label.setText(f"Saved recipe {recipe.id[:8]} with {len(recipe.plan.steps)} action(s).")

    def refine_current_plan(self) -> None:
        if self.latest_summary is None:
            self.run_dry_run()
            return
        refinement = self.request_input.text().strip()
        if not refinement:
            self.set_error("Refinement input is empty.")
            return
        try:
            trace = self.storage.get_trace(self.latest_summary.trace_id)
        except KeyError as exc:
            self.set_error(str(exc))
            return
        original_goal = (
            trace.request.plan_refinement.original_goal
            if trace.request.plan_refinement is not None
            else self.active_draft_goal or trace.request.user_request
        )
        if refinement.strip() == original_goal.strip():
            self.debug_snapshot_text.setPlainText(
                "Type the change you want to make to the current draft, then click Refine."
            )
            return
        revision_index = (
            trace.request.plan_refinement.revision_index + 1
            if trace.request.plan_refinement is not None
            else len(self.active_draft_refinements) + 1
        )
        refinement_context = build_plan_refinement_context(
            original_goal=original_goal,
            current_plan=trace.planner_result.action_plan,
            user_refinement=refinement,
            recipe_id=self.active_recipe_id,
            revision_index=revision_index,
        )
        request = WorkflowRequest(
            user_request=(
                f"Refine the draft plan for this goal: {original_goal}\n"
                f"User refinement: {refinement}"
            ),
            task_title=trace.request.task_title or original_goal,
            scene_name=self.active_recipe_id,
            run_mode=RunMode.DRY_RUN,
            plan_refinement=refinement_context,
        )
        self.active_draft_goal = original_goal
        self.summary_label.setText("Refining the current draft plan.")
        self._run_workflow_dry_run(request)
