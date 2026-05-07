from __future__ import annotations

from ..capabilities import DEFAULT_CAPABILITY_REGISTRY, CapabilityRegistry
from ..models import ContextSnapshot, PlannerResult, WorkflowRequest
from ..prompting import PromptTemplateLibrary, load_app_inventory_summary
from .openai_client import OpenAIResponsesClient
from .openai_planner_helpers import is_unsupported_destructive_file_request
from .openai_planner_intent import OpenAIPlannerIntentMixin
from .openai_planner_inventory import OpenAIPlannerInventoryMixin
from .openai_planner_normalization import OpenAIPlannerNormalizationMixin
from .openai_planner_safety import OpenAIPlannerSafetyMixin
from .openai_schemas import planner_result_schema
from .windows_app_discovery import ApplicationInventoryStore


class RealPlanner(
    OpenAIPlannerSafetyMixin,
    OpenAIPlannerInventoryMixin,
    OpenAIPlannerIntentMixin,
    OpenAIPlannerNormalizationMixin,
):
    """Planner implementation backed by a real Responses API provider."""

    def __init__(
        self,
        client: OpenAIResponsesClient,
        prompt_library: PromptTemplateLibrary | None = None,
        capability_registry: CapabilityRegistry | None = None,
        enable_fast_inventory: bool = True,
    ) -> None:
        self.client = client
        self.prompt_library = prompt_library or PromptTemplateLibrary.default()
        self.capability_registry = capability_registry or DEFAULT_CAPABILITY_REGISTRY
        self.app_inventory_store = ApplicationInventoryStore()
        self.enable_fast_inventory = enable_fast_inventory

    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        if is_unsupported_destructive_file_request(request.user_request):
            return self._unsupported_destructive_file_plan(request)

        if self.enable_fast_inventory:
            inventory_result = self._model_inventory_plan(request, context)
            if inventory_result is not None:
                return inventory_result

        allowed_actions = self.capability_registry.allowed_action_values()
        app_inventory_summary = load_app_inventory_summary(
            path=self.app_inventory_store.path,
            query=request.user_request,
        )
        intent_interpretation, selected_intent_template = self._interpret_intent_with_template(
            request=request,
            context=context,
            app_inventory_summary=app_inventory_summary,
        )
        rendered_prompt = self.prompt_library.render_planner_prompt(
            request=request,
            context=context,
            allowed_actions=allowed_actions,
            app_inventory_summary=app_inventory_summary,
            intent_interpretation=intent_interpretation,
            capability_summary=self.capability_registry.prompt_summary(),
        )
        payload = {
            "user_request": request.user_request,
            "task_title": request.task_title,
            "scene_name": request.scene_name,
            "recovery_context": (
                request.recovery_context.model_dump(mode="json")
                if request.recovery_context is not None
                else None
            ),
            "plan_refinement": (
                request.plan_refinement.model_dump(mode="json")
                if request.plan_refinement is not None
                else None
            ),
            "context": context.model_dump(mode="json"),
            "allowed_actions": allowed_actions,
            "capability_registry": self.capability_registry.to_provider_payload(),
            "intent_interpretation": intent_interpretation.model_dump(mode="json"),
            "selected_prompt_template": rendered_prompt.template_id,
            "planning_process": [
                "read_prior_intent_interpretation",
                "select_capability",
                "draft_candidate_steps",
                "validate_against_allowed_actions",
                "return_planner_result",
            ],
        }
        result = self.client.create_json_response(
            model=self.client.config.model,
            system_prompt=rendered_prompt.system_prompt,
            user_payload=payload,
            schema_name="planner_result",
            schema=planner_result_schema(),
            trace_id=None,
        )
        planner_result = PlannerResult.model_validate(result)
        planner_result.intent_interpretation = intent_interpretation
        planner_result.selected_intent_template = selected_intent_template
        planner_result.selected_planner_template = rendered_prompt.template_id
        return self._normalize_planner_result(request, planner_result)
