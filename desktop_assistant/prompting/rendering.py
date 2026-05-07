from __future__ import annotations

from pathlib import Path

from ..models import IntentInterpretation, WorkflowRequest


def default_template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts" / "reusable_templates.json"


def fill_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def intent_interpretation_summary(intent: IntentInterpretation | None) -> str:
    if intent is None:
        return "No prior intent interpretation was provided."
    return "\n".join(
        [
            f"user_goal={intent.user_goal}",
            f"primary_intent={intent.primary_intent}",
            f"target_kind={intent.target_kind}",
            f"target_name={intent.target_name}",
            f"confidence={intent.confidence}",
            f"needs_clarification={intent.needs_clarification}",
            f"clarification_question={intent.clarification_question or ''}",
            f"reasoning_summary={intent.reasoning_summary}",
        ]
    )


def recovery_context_summary(request: WorkflowRequest) -> str:
    if request.recovery_context is None:
        return "No prior execution failure was provided."
    context = request.recovery_context
    return "\n".join(
        [
            f"original_user_request={context.original_user_request}",
            f"failed_step_index={context.failed_step_index}",
            f"failed_action_type={context.failed_action_type}",
            f"failed_target={context.failed_target}",
            f"failure_status={context.failure_status}",
            f"failure_code={context.failure_code or ''}",
            f"failure_message={context.failure_message}",
            f"suggested_remedy={context.suggested_remedy or ''}",
            f"failed_attempts_for_action={context.failed_attempts_for_action}",
            f"recovery_attempt={context.recovery_attempt}",
            f"recovery_category={context.recovery_category or ''}",
            f"recovery_strategy={context.recovery_strategy or ''}",
            "recovery_guidance="
            + ("; ".join(context.recovery_guidance) if context.recovery_guidance else ""),
        ]
    )


def plan_refinement_summary(request: WorkflowRequest) -> str:
    if request.plan_refinement is None:
        return "No active draft-plan refinement was provided."
    context = request.plan_refinement
    lines = [
        f"original_goal={context.original_goal}",
        f"user_refinement={context.user_refinement}",
        f"revision_index={context.revision_index}",
        f"recipe_id={context.recipe_id or ''}",
        f"current_plan_name={context.current_plan.plan_name}",
        f"current_plan_source={context.current_plan.source}",
        "current_steps:",
    ]
    if context.current_plan.steps:
        for index, step in enumerate(context.current_plan.steps, start=1):
            lines.append(
                f"{index}. {step.action_type.value} -> {step.target} "
                f"[{step.risk_level.value}] {step.reason}"
            )
    else:
        lines.append("(No current steps)")
    if context.constraints:
        lines.append("constraints:")
        lines.extend(f"- {constraint}" for constraint in context.constraints)
    return "\n".join(lines)


_default_template_path = default_template_path
_fill_template = fill_template
_intent_interpretation_summary = intent_interpretation_summary
_recovery_context_summary = recovery_context_summary
_plan_refinement_summary = plan_refinement_summary
