from __future__ import annotations

from ..capabilities import DEFAULT_CAPABILITY_REGISTRY, CapabilityRegistry
from ..models import (
    ActionType,
    ContextSnapshot,
    PlannerResult,
    PolicyDecision,
    ReviewResult,
    WorkflowRequest,
)
from ..prompting import PromptTemplateLibrary
from .provider_factory import LLMClient
from .openai_schemas import review_result_schema


class RealReviewer:
    """Reviewer implementation backed by a real Responses API provider."""

    def __init__(
        self,
        client: LLMClient,
        prompt_library: PromptTemplateLibrary | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.client = client
        self.prompt_library = prompt_library or PromptTemplateLibrary.default()
        self.capability_registry = capability_registry or DEFAULT_CAPABILITY_REGISTRY

    def review(
        self,
        request: WorkflowRequest,
        planner_result: PlannerResult,
        policy_decision: PolicyDecision,
        context: ContextSnapshot,
    ) -> ReviewResult:
        clarification_result = self._fast_clarification_review(planner_result, policy_decision)
        if clarification_result is not None:
            return clarification_result

        fast_result = self._fast_safe_review(planner_result, policy_decision)
        if fast_result is not None:
            return fast_result

        rendered_prompt = self.prompt_library.render_reviewer_prompt(request=request)
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
            "planner_result": planner_result.model_dump(mode="json"),
            "policy_decision": policy_decision.model_dump(mode="json"),
            "capability_registry": self.capability_registry.to_provider_payload(),
            "selected_prompt_template": rendered_prompt.template_id,
            "review_process": [
                "check_request_alignment",
                "check_allowed_actions",
                "check_target_specificity",
                "check_policy_consistency",
                "return_review_result",
            ],
        }
        result = self.client.create_json_response(
            model=self.client.config.review_model,
            system_prompt=rendered_prompt.system_prompt,
            user_payload=payload,
            schema_name="review_result",
            schema=review_result_schema(),
            trace_id=None,
        )
        return ReviewResult.model_validate(result)

    @staticmethod
    def _fast_clarification_review(
        planner_result: PlannerResult,
        policy_decision: PolicyDecision,
    ) -> ReviewResult | None:
        if not planner_result.requires_clarification and planner_result.action_plan.steps:
            return None

        issues: list[str] = []
        if planner_result.requires_clarification:
            issues.append("Planner requires clarification before any action can be executed.")
        if not planner_result.action_plan.steps:
            issues.append("Planner returned no executable steps.")
        issues.extend(f"{issue.code}: {issue.message}" for issue in policy_decision.issues)

        return ReviewResult(
            approved=False,
            risk_level=policy_decision.risk_level,
            needs_user_confirmation=True,
            review_summary="Clarification or a safer plan is required before execution.",
            issues=issues,
            rejection_reason="The current plan is not executable until the user clarifies the request.",
        )

    @staticmethod
    def _fast_safe_review(
        planner_result: PlannerResult,
        policy_decision: PolicyDecision,
    ) -> ReviewResult | None:
        steps = planner_result.action_plan.steps
        if planner_result.action_plan.source not in {"inventory_fast_path", "model_inventory_path"}:
            return None
        if len(steps) != 1:
            return None
        step = steps[0]
        if step.action_type not in {ActionType.OPEN_APP, ActionType.FOCUS_APP}:
            return None
        if not policy_decision.approved or policy_decision.requires_user_confirmation:
            return None
        return ReviewResult(
            approved=True,
            risk_level=policy_decision.risk_level,
            needs_user_confirmation=False,
            review_summary=(
                "Fast local review approved a single low-risk app action resolved through app_inventory."
            ),
            issues=[],
            rejection_reason=None,
        )
