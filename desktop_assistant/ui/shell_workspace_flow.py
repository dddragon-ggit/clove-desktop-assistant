from __future__ import annotations

from ..models import ActionStep
from ..input_router import InputRoute, InputRouteType
from . import shell_text
from .shell_workspace_actions import (
    ACTION_ROLE,
    append_action_from_input,
    edited_suggestion,
    populate_action_list,
    remove_selected_action,
    update_selected_action_from_input,
)
from .shell_workspace_target import browse_target, configure_target_input, set_target_text, target_text
from .shell_workspace_view import workspace_suggestion_text


class ShellWorkspaceFlowMixin:
    def _submit_text(self, value: str, accepted: bool, *, return_to: str | None = None) -> None:
        route = self.controller.route_input(value, prediction=self.current_prediction, accepted_prediction=accepted)
        if route.route_type == InputRouteType.TODO:
            if route.target_id and self._open_todo_route(route.target_id):
                return
            self._show_todo_page()
        elif route.route_type in {InputRouteType.WORKSPACE, InputRouteType.CONTINUE_WORK}:
            self._quick_prepare_workspace(route, return_to=return_to)
        else:
            self._run_dry_run(route.normalized_text or value)

    def _quick_prepare_workspace(self, route: InputRoute, *, return_to: str | None = None) -> None:
        suggestion = self.controller.pending_workspace_draft(route.target_id)
        if suggestion is None:
            goal = route.normalized_text.strip()
            if not goal:
                self._show_workspace_page()
                return
            suggestion = self.controller.workspace_recipe_for_goal(goal) or self.controller.workspace_from_goal(goal)
        self.current_suggestion = suggestion
        self.workspace_input.setText(suggestion.goal)
        self._render_workspace()
        self._refresh_home()
        if suggestion.plan.steps:
            self._show_workspace_confirmation(suggestion, return_to=return_to)
            return
        if route.reason == "direct workspace action":
            self._run_dry_run(route.normalized_text)
            return
        self._show_workspace_page()

    def _generate_workspace(self) -> None:
        goal = self.workspace_input.text().strip()
        if not goal:
            return
        self.current_suggestion = self.controller.workspace_recipe_for_goal(goal) or self.controller.workspace_from_goal(goal)
        self._render_workspace()
        self._refresh_home()

    def _refine_workspace(self) -> None:
        if self.current_suggestion is None:
            self._generate_workspace()
            return
        feedback = self.feedback_input.text().strip()
        if feedback:
            self.current_suggestion = self._current_workspace_plan_suggestion() or self.current_suggestion
            self.current_suggestion = self.controller.refine_workspace(self.current_suggestion, feedback)
            self.feedback_input.clear()
            self._render_workspace()

    def _save_workspace(self) -> None:
        suggestion = self._current_workspace_plan_suggestion()
        if suggestion is not None:
            recipe = self.controller.save_workspace_recipe(suggestion, name=self._workspace_recipe_name(suggestion))
            self.current_suggestion = self.controller.save_workspace_draft(suggestion)
            self._refresh_workspace_recipe_options(selected_id=recipe.id)
            self.workspace_text.append(shell_text.WORKSPACE_RECIPE_SAVED.format(name=recipe.name))

    def _plan_workspace_goal(self) -> None:
        goal = self.workspace_input.text().strip()
        if self.current_suggestion is None or (goal and self.current_suggestion.goal != goal):
            self._generate_workspace()
        suggestion = self._current_workspace_plan_suggestion()
        if suggestion is None:
            return
        if not suggestion.plan.steps:
            self.workspace_text.append(f"\n{shell_text.WORKSPACE_NEEDS_MORE_DETAIL}")
            return
        self.current_suggestion = suggestion
        self._show_workspace_confirmation(suggestion, return_to="workspace")

    def _render_workspace(self) -> None:
        if self.current_suggestion is not None:
            self.workspace_text.setPlainText(workspace_suggestion_text(self.current_suggestion))
            populate_action_list(self.workspace_plan_action_list, self.current_suggestion)
            self._workspace_plan_action_type_changed()

    def _show_workspace_page(self) -> None:
        self._show_panel()
        self._ensure_workspace_page_geometry()
        self._refresh_workspace_recipe_options()
        self.stack.setCurrentWidget(self.workspace_page)

    def _load_workspace_recipe(self) -> None:
        recipe_id = self.workspace_recipe_combo.currentData()
        if not recipe_id:
            return
        suggestion = self.controller.workspace_from_recipe(str(recipe_id))
        if suggestion is None:
            self.workspace_text.append(shell_text.WORKSPACE_RECIPE_LOAD_FAILED)
            return
        self.current_suggestion = suggestion
        self.workspace_input.setText(suggestion.goal)
        self._render_workspace()
        self.workspace_text.append(shell_text.WORKSPACE_RECIPE_LOADED.format(name=suggestion.title))

    def _add_workspace_plan_action(self) -> None:
        action_type = str(self.workspace_plan_action_type_combo.currentData() or "")
        target = self._normalized_workspace_plan_target(action_type, target_text(self.workspace_plan_action_target_input))
        if append_action_from_input(self.workspace_plan_action_list, action_type, target):
            set_target_text(self.workspace_plan_action_target_input, "")
            self._sync_workspace_plan_from_editor()

    def _update_workspace_plan_action(self) -> None:
        action_type = str(self.workspace_plan_action_type_combo.currentData() or "")
        target = self._normalized_workspace_plan_target(action_type, target_text(self.workspace_plan_action_target_input))
        if update_selected_action_from_input(self.workspace_plan_action_list, action_type, target):
            self._sync_workspace_plan_from_editor()

    def _remove_workspace_plan_action(self) -> None:
        if remove_selected_action(self.workspace_plan_action_list):
            self._sync_workspace_plan_from_editor()

    def _workspace_plan_action_type_changed(self) -> None:
        action_type = str(self.workspace_plan_action_type_combo.currentData() or "")
        configure_target_input(
            self.workspace_plan_action_target_input,
            action_type,
            self.controller.app_options() if action_type in {"open_app", "focus_app"} else [],
            self.workspace_plan_action_browse_button,
        )

    def _workspace_plan_action_selected(self) -> None:
        item = self.workspace_plan_action_list.currentItem()
        if item is None:
            return
        payload = item.data(ACTION_ROLE)
        if not isinstance(payload, dict):
            return
        action = ActionStep.model_validate(payload)
        index = self.workspace_plan_action_type_combo.findData(action.action_type.value)
        if index >= 0:
            self.workspace_plan_action_type_combo.setCurrentIndex(index)
        set_target_text(self.workspace_plan_action_target_input, action.target)

    def _workspace_plan_actions_changed(self) -> None:
        self._sync_workspace_plan_from_editor()

    def _browse_workspace_plan_action_target(self) -> None:
        action_type = str(self.workspace_plan_action_type_combo.currentData() or "")
        selected = browse_target(self, action_type)
        if selected:
            set_target_text(self.workspace_plan_action_target_input, selected)

    def _current_workspace_plan_suggestion(self):
        return edited_suggestion(self.current_suggestion, self.workspace_plan_action_list)

    def _normalized_workspace_plan_target(self, action_type: str, target: str) -> str:
        if action_type in {"open_app", "focus_app"}:
            return self.controller.resolve_app_name(target)
        return target.strip()

    def _sync_workspace_plan_from_editor(self) -> None:
        suggestion = self._current_workspace_plan_suggestion()
        if suggestion is not None:
            self.current_suggestion = suggestion
            self.workspace_text.setPlainText(workspace_suggestion_text(suggestion))

    def _refresh_workspace_recipe_options(self, *, selected_id: str | None = None) -> None:
        current = selected_id or self.workspace_recipe_combo.currentData()
        self.workspace_recipe_combo.blockSignals(True)
        self.workspace_recipe_combo.clear()
        self.workspace_recipe_combo.addItem(shell_text.WORKSPACE_RECIPE_PICKER_PLACEHOLDER, "")
        for recipe in self.controller.workspace_recipes():
            self.workspace_recipe_combo.addItem(f"{recipe.name} · {len(recipe.plan.steps)} 个动作", recipe.id)
        index = self.workspace_recipe_combo.findData(current) if current else 0
        self.workspace_recipe_combo.setCurrentIndex(index if index >= 0 else 0)
        self.workspace_recipe_combo.blockSignals(False)

    def _workspace_recipe_name(self, suggestion) -> str:  # type: ignore[no-untyped-def]
        return self.workspace_input.text().strip() or suggestion.goal or suggestion.title
