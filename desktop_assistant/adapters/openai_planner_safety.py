from __future__ import annotations

from ..models import ActionPlan, IntentInterpretation, PlannerResult, RiskLevel, WorkflowRequest


class OpenAIPlannerSafetyMixin:
    def _unsupported_destructive_file_plan(self, request: WorkflowRequest) -> PlannerResult:
        intent = IntentInterpretation(
            user_goal=request.user_request,
            primary_intent="unknown",
            target_kind="file_path",
            target_name=request.user_request,
            confidence="high",
            needs_clarification=True,
            clarification_question="这个请求涉及删除或清空文件，请先明确具体目标和可恢复方案。",
            reasoning_summary="Unsupported destructive file operation; do not create executable steps.",
        )
        return PlannerResult(
            intent_summary="需要先澄清并阻止执行高风险文件删除/清空操作。",
            requires_clarification=True,
            action_plan=ActionPlan(
                plan_name="clarify-destructive-file-operation",
                source="safety_normalizer",
                steps=[],
            ),
            risk_guess=RiskLevel.HIGH,
            reasoning_summary=(
                "The request implies destructive file cleanup, but this assistant has no safe "
                "delete/empty-recycle-bin capability."
            ),
            intent_interpretation=intent,
            selected_intent_template="intent.default",
            selected_planner_template="planner.default",
        )
