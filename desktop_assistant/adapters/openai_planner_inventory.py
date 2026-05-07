from __future__ import annotations

import json

from ..models import AppIntentMatch, ActionPlan, ActionStep, ActionType, IntentInterpretation, PlannerResult, RiskLevel, WorkflowRequest
from ..prompting import load_app_candidate_summary, load_app_name_index_summary
from .openai_client import ProviderResponseError
from .openai_planner_helpers import fast_inventory_action_type
from .openai_schemas import app_intent_match_schema


class OpenAIPlannerInventoryMixin:
    def _model_inventory_plan(self, request: WorkflowRequest, context) -> PlannerResult | None:  # noqa: ANN001
        if request.recovery_context is not None:
            return None
        action_hint = fast_inventory_action_type(request.user_request)
        if action_hint is None:
            return None
        if action_hint.value not in self.capability_registry.allowed_action_values():
            return None
        try:
            inventory = self.app_inventory_store.ensure(refresh=False)
        except (FileNotFoundError, json.JSONDecodeError, OSError, KeyError, ValueError):
            return None

        try:
            match = self._match_app_intent_with_model(request=request, action_hint=action_hint)
        except ProviderResponseError:
            return self._fast_inventory_plan(request)

        if not match.local_app_request or match.action_type == "none":
            return None
        if match.action_type not in {ActionType.OPEN_APP.value, ActionType.FOCUS_APP.value}:
            return None

        action_type = ActionType(match.action_type)
        if action_type.value not in self.capability_registry.allowed_action_values():
            return None
        app = inventory.find(match.target_name)
        if app is None and not match.needs_clarification and match.confidence != "low":
            app = inventory.find(request.user_request)
        if app is None or not app.executable_path:
            return self._inventory_clarification_plan(request, match)
        return self._inventory_match_plan(
            request=request,
            app=app,
            action_type=action_type,
            source="model_inventory_path",
            reason=(
                "Model-assisted local app match using app_name_index.json; "
                f"matched request to installed app {app.name}."
            ),
            intent_reasoning=match.reasoning_summary,
            selected_intent_template="app_match.local_app",
        )

    def _match_app_intent_with_model(
        self,
        *,
        request: WorkflowRequest,
        action_hint: ActionType,
    ) -> AppIntentMatch:
        app_name_index_summary = load_app_name_index_summary(
            path=self.app_inventory_store.path,
            name_index_path=self.app_inventory_store.name_index_path,
        )
        candidate_app_summary = load_app_candidate_summary(
            query=request.user_request,
            path=self.app_inventory_store.path,
            name_index_path=self.app_inventory_store.name_index_path,
        )
        rendered_prompt = self.prompt_library.render_app_match_prompt(
            request=request,
            app_name_index_summary=app_name_index_summary,
            candidate_app_summary=candidate_app_summary,
        )
        payload = {
            "user_request": request.user_request,
            "candidate_action_hint": action_hint.value,
            "candidate_app_summary": candidate_app_summary,
            "app_name_index_summary": app_name_index_summary,
            "selected_prompt_template": rendered_prompt.template_id,
            "matching_process": [
                "read_user_request",
                "review_high_relevance_candidate_shortlist",
                "compare_target_against_app_name_index",
                "classify_open_focus_or_not_local_app",
                "return_exact_inventory_display_name_when_confident",
            ],
        }
        result = self.client.create_json_response(
            model=self.client.config.model,
            system_prompt=rendered_prompt.system_prompt,
            user_payload=payload,
            schema_name="app_intent_match",
            schema=app_intent_match_schema(),
            trace_id=None,
        )
        return AppIntentMatch.model_validate(result)

    def _fast_inventory_plan(self, request: WorkflowRequest) -> PlannerResult | None:
        if request.recovery_context is not None:
            return None
        action_type = fast_inventory_action_type(request.user_request)
        if action_type is None:
            return None
        if action_type.value not in self.capability_registry.allowed_action_values():
            return None
        try:
            inventory = self.app_inventory_store.ensure(refresh=False)
        except (FileNotFoundError, json.JSONDecodeError, OSError, KeyError, ValueError):
            return None
        app = inventory.find(request.user_request)
        if app is None or not app.executable_path:
            return None
        return self._inventory_match_plan(
            request=request,
            app=app,
            action_type=action_type,
            source="inventory_fast_path",
            reason=(
                f"Deterministic local inventory fallback: the request targets installed app {app.name}. "
                "The lightweight model app match was unavailable."
            ),
            intent_reasoning="Resolved by deterministic app_inventory fallback.",
            selected_intent_template="intent.local_app",
        )

    def _inventory_match_plan(
        self,
        *,
        request: WorkflowRequest,
        app,
        action_type: ActionType,
        source: str,
        reason: str,
        intent_reasoning: str,
        selected_intent_template: str,
    ) -> PlannerResult:
        action = ActionStep(
            action_type=action_type,
            target=app.name,
            params={
                "executable_path": app.executable_path,
                "app_inventory_source": app.source,
                "planner_fast_path": source,
            },
            risk_level=RiskLevel.LOW,
            reason=reason,
        )
        intent = IntentInterpretation(
            user_goal=request.user_request,
            primary_intent="open_local_app",
            target_kind="local_app",
            target_name=app.name,
            confidence="high",
            needs_clarification=False,
            clarification_question=None,
            reasoning_summary=intent_reasoning,
        )
        template_id = "planner.local_app"
        return PlannerResult(
            intent_summary=f"Open installed local application: {app.name}",
            requires_clarification=False,
            action_plan=ActionPlan(
                plan_name="open-local-app" if action_type == ActionType.OPEN_APP else "focus-local-app",
                source=source,
                steps=[action],
            ),
            risk_guess=RiskLevel.LOW,
            reasoning_summary=reason,
            intent_interpretation=intent,
            selected_intent_template=selected_intent_template,
            selected_planner_template=template_id,
        )

    def _inventory_clarification_plan(self, request: WorkflowRequest, match: AppIntentMatch) -> PlannerResult:
        question = match.clarification_question or "Which installed application should I open?"
        intent = IntentInterpretation(
            user_goal=request.user_request,
            primary_intent="open_local_app",
            target_kind="local_app",
            target_name=match.target_name,
            confidence=match.confidence,
            needs_clarification=True,
            clarification_question=question,
            reasoning_summary=match.reasoning_summary,
        )
        return PlannerResult(
            intent_summary=question,
            requires_clarification=True,
            action_plan=ActionPlan(
                plan_name="clarify-local-app",
                source="model_inventory_path",
                steps=[],
            ),
            risk_guess=RiskLevel.LOW,
            reasoning_summary=match.reasoning_summary,
            intent_interpretation=intent,
            selected_intent_template="app_match.local_app",
            selected_planner_template="planner.local_app",
        )
