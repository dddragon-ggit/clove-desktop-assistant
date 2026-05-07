from __future__ import annotations

from ..action_trust import ActionTrustStore, action_trust_key
from ..core.policy import PolicyEngine
from ..models import ActionPlan, PolicyDecision
from .models import ActionConfirmationCard, ConfirmationApplyResult, ConfirmationChoice, ConfirmationFlow


class ConfirmationService:
    """Frontend-friendly wrapper for policy decisions and action-level trust."""

    def __init__(
        self,
        *,
        policy_engine: PolicyEngine | None = None,
        trust_store: ActionTrustStore | None = None,
    ) -> None:
        self.trust_store = trust_store or ActionTrustStore()
        self.policy_engine = policy_engine or PolicyEngine(trusted_action_keys=self.trust_store.trusted_keys())

    def build_flow(
        self,
        plan: ActionPlan,
        *,
        policy_decision: PolicyDecision | None = None,
    ) -> ConfirmationFlow:
        if policy_decision is None:
            self.policy_engine.trusted_action_keys = self.trust_store.trusted_keys()
            decision = self.policy_engine.evaluate(plan)
        else:
            decision = policy_decision
        choices = [ConfirmationChoice.REJECT]
        if decision.approved:
            choices.append(ConfirmationChoice.RUN_ONCE)
            if decision.requires_user_confirmation:
                choices.append(ConfirmationChoice.TRUST_ALWAYS)
        return ConfirmationFlow(
            approved_by_policy=decision.approved,
            requires_user_confirmation=decision.requires_user_confirmation,
            choices=choices,
            action_cards=[
                ActionConfirmationCard(
                    step_index=item.step_index,
                    action_type=item.action_type.value,
                    target=item.target,
                    risk_level=item.risk_level.value,
                    requires_confirmation=item.requires_confirmation,
                    whitelisted=item.whitelisted,
                    reason=item.reason,
                    trust_key=action_trust_key(plan.steps[item.step_index]),
                )
                for item in decision.action_decisions
            ],
            issues=[issue.message for issue in decision.issues],
        )

    def apply_choice(self, plan: ActionPlan, choice: ConfirmationChoice) -> ConfirmationApplyResult:
        if choice == ConfirmationChoice.REJECT:
            return ConfirmationApplyResult(choice=choice, accepted=False, message="User rejected the plan.")
        if choice == ConfirmationChoice.RUN_ONCE:
            return ConfirmationApplyResult(choice=choice, accepted=True, message="Plan accepted for this run.")
        flow = self.build_flow(plan)
        trusted: list[str] = []
        for card in flow.action_cards:
            if not card.requires_confirmation:
                continue
            action = plan.steps[card.step_index]
            rule = self.trust_store.trust_action(action, action.risk_level, note="Trusted from confirmation flow.")
            trusted.append(rule.key)
        self.policy_engine.trusted_action_keys = self.trust_store.trusted_keys()
        return ConfirmationApplyResult(
            choice=choice,
            accepted=True,
            trusted_keys=trusted,
            message=f"Trusted {len(trusted)} action(s).",
        )
