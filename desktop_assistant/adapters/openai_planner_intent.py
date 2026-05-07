from __future__ import annotations

from ..models import ContextSnapshot, IntentInterpretation, WorkflowRequest
from .openai_schemas import intent_interpretation_schema


class OpenAIPlannerIntentMixin:
    def interpret_intent(
        self,
        *,
        request: WorkflowRequest,
        context: ContextSnapshot,
        app_inventory_summary: str,
    ) -> IntentInterpretation:
        intent_interpretation, _template_id = self._interpret_intent_with_template(
            request=request,
            context=context,
            app_inventory_summary=app_inventory_summary,
        )
        return intent_interpretation

    def _interpret_intent_with_template(
        self,
        *,
        request: WorkflowRequest,
        context: ContextSnapshot,
        app_inventory_summary: str,
    ) -> tuple[IntentInterpretation, str]:
        rendered_prompt = self.prompt_library.render_intent_prompt(
            request=request,
            app_inventory_summary=app_inventory_summary,
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
            "app_inventory_summary": app_inventory_summary,
            "capability_registry": self.capability_registry.to_provider_payload(),
            "selected_prompt_template": rendered_prompt.template_id,
            "intent_process": [
                "read_user_request",
                "compare_against_app_inventory",
                "separate_local_app_vs_website_vs_lookup",
                "decide_if_clarification_is_needed",
                "return_intent_interpretation",
            ],
        }
        result = self.client.create_json_response(
            model=self.client.config.model,
            system_prompt=rendered_prompt.system_prompt,
            user_payload=payload,
            schema_name="intent_interpretation",
            schema=intent_interpretation_schema(),
            trace_id=None,
        )
        return IntentInterpretation.model_validate(result), rendered_prompt.template_id
