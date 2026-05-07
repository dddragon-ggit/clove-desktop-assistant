from __future__ import annotations

from ..models import ContextSnapshot, PlannerResult, PolicyDecision, ReviewResult, RiskLevel, WorkflowRequest


class FakeReviewer:
    """Deterministic reviewer used before real safety model integration."""

    def review(
        self,
        request: WorkflowRequest,
        planner_result: PlannerResult,
        policy_decision: PolicyDecision,
        context: ContextSnapshot,
    ) -> ReviewResult:
        if not policy_decision.approved:
            return ReviewResult(
                approved=False,
                risk_level=policy_decision.risk_level,
                needs_user_confirmation=True,
                review_summary="规则引擎已拒绝该动作计划。",
                issues=[issue.message for issue in policy_decision.issues],
                rejection_reason="Blocked by policy engine.",
            )

        if planner_result.requires_clarification:
            return ReviewResult(
                approved=False,
                risk_level=RiskLevel.MEDIUM,
                needs_user_confirmation=True,
                review_summary="规划结果存在歧义，需要用户确认。",
                issues=["Planner requested clarification."],
                rejection_reason="Planner requested clarification.",
            )

        return ReviewResult(
            approved=True,
            risk_level=policy_decision.risk_level,
            needs_user_confirmation=policy_decision.requires_user_confirmation,
            review_summary=f"FakeReviewer 在 {context.weekday} 审查通过该动作计划。",
            issues=[],
            rejection_reason=None,
        )
