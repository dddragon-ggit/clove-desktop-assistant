from __future__ import annotations

import json

from ..models import ActionType, PlannerResult, WorkflowRequest
from .openai_planner_helpers import is_current_workspace_reference


class OpenAIPlannerNormalizationMixin:
    def _normalize_planner_result(
        self,
        request: WorkflowRequest,
        planner_result: PlannerResult,
    ) -> PlannerResult:
        self._normalize_single_answer_query_target(request, planner_result)
        self._normalize_current_workspace_target(request, planner_result)
        self._normalize_list_windows_target(planner_result)
        return self._ground_open_app_steps(planner_result)

    @staticmethod
    def _normalize_single_answer_query_target(
        request: WorkflowRequest,
        planner_result: PlannerResult,
    ) -> None:
        steps = planner_result.action_plan.steps
        if len(steps) != 1 or steps[0].action_type != ActionType.ANSWER_QUERY:
            return
        normalized = request.user_request.strip()
        if normalized:
            steps[0].target = normalized

    @staticmethod
    def _normalize_current_workspace_target(
        request: WorkflowRequest,
        planner_result: PlannerResult,
    ) -> None:
        for step in planner_result.action_plan.steps:
            if step.action_type != ActionType.OPEN_PROJECT:
                continue
            if is_current_workspace_reference(request.user_request, step.target):
                step.target = "current workspace"

    @staticmethod
    def _normalize_list_windows_target(planner_result: PlannerResult) -> None:
        for step in planner_result.action_plan.steps:
            if step.action_type == ActionType.LIST_WINDOWS:
                step.target = "visible"

    def _ground_open_app_steps(self, planner_result: PlannerResult) -> PlannerResult:
        try:
            inventory = self.app_inventory_store.load()
        except (FileNotFoundError, json.JSONDecodeError, OSError, KeyError, ValueError):
            return planner_result

        for step in planner_result.action_plan.steps:
            if step.action_type != ActionType.OPEN_APP:
                continue
            app = inventory.find(step.target)
            if app is None or not app.executable_path:
                continue
            step.target = app.name
            step.params = {
                **step.params,
                "executable_path": app.executable_path,
                "app_inventory_source": app.source,
            }
        return planner_result
