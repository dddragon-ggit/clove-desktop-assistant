from __future__ import annotations

from collections.abc import Iterable

from ..capabilities import CapabilityRegistry
from ..action_trust import action_trust_key
from ..models import ActionDecision, ActionPlan, ActionType, PolicyDecision, PolicyIssue, RiskLevel


class PolicyEngine:
    """Hard rule checks that stay independent from AI behavior."""

    def __init__(
        self,
        allowed_actions: Iterable[ActionType] | None = None,
        capability_registry: CapabilityRegistry | None = None,
        trusted_action_keys: Iterable[str] | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry.default()
        default_allowed = {ActionType(value) for value in self.capability_registry.allowed_action_values()}
        self.allowed_actions = default_allowed if allowed_actions is None else set(allowed_actions)
        self.trusted_action_keys = set(trusted_action_keys or ())

    def evaluate(self, action_plan: ActionPlan, planner_risk_guess: RiskLevel | None = None) -> PolicyDecision:
        issues: list[PolicyIssue] = []
        action_decisions: list[ActionDecision] = []
        max_risk = planner_risk_guess or RiskLevel.LOW

        for index, step in enumerate(action_plan.steps):
            if step.action_type not in self.allowed_actions:
                issues.append(
                    PolicyIssue(
                        code="ACTION_NOT_ALLOWED",
                        message=f"Action {step.action_type.value} is not allowed.",
                    )
                )
            issues.extend(self.capability_registry.validate_action(step))
            effective_risk = self.capability_registry.effective_risk(step)
            whitelisted = action_trust_key(step) in self.trusted_action_keys
            requires_confirmation = (
                effective_risk in {RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL}
                and not whitelisted
            )
            action_decisions.append(
                ActionDecision(
                    step_index=index,
                    action_type=step.action_type,
                    target=step.target,
                    risk_level=effective_risk,
                    requires_confirmation=requires_confirmation,
                    whitelisted=whitelisted,
                    reason=(
                        "Trusted action whitelist matched."
                        if whitelisted
                        else "Medium or higher risk action needs confirmation."
                        if requires_confirmation
                        else "Low-risk action does not need confirmation."
                    ),
                )
            )
            if self._risk_rank(effective_risk) > self._risk_rank(max_risk):
                max_risk = effective_risk

        if (
            planner_risk_guess in {RiskLevel.HIGH, RiskLevel.CRITICAL}
            and self._risk_rank(planner_risk_guess) > self._highest_step_risk(action_plan)
        ):
            issues.append(
                PolicyIssue(
                    code="PLANNER_RISK_ELEVATED",
                    message=f"Planner estimated overall risk as {planner_risk_guess.value}.",
                )
            )

        if max_risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            issues.append(
                PolicyIssue(
                    code="RISK_TOO_HIGH",
                    message="High-risk and critical actions are blocked in the current prototype.",
                )
            )

        approved = not issues
        return PolicyDecision(
            approved=approved,
            risk_level=max_risk,
            requires_user_confirmation=(
                any(decision.requires_confirmation for decision in action_decisions)
                or max_risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}
            ),
            issues=issues,
            action_decisions=action_decisions,
        )

    @staticmethod
    def _risk_rank(level: RiskLevel) -> int:
        order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }
        return order[level]

    def _highest_step_risk(self, action_plan: ActionPlan) -> int:
        highest = self._risk_rank(RiskLevel.LOW)
        for step in action_plan.steps:
            effective = self.capability_registry.effective_risk(step)
            highest = max(highest, self._risk_rank(effective))
        return highest
