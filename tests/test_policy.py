from __future__ import annotations

import unittest

from desktop_assistant.core.policy import PolicyEngine
from desktop_assistant.models import ActionPlan, ActionStep, ActionType, RiskLevel


class PolicyEngineTests(unittest.TestCase):
    def test_planner_medium_risk_does_not_force_low_risk_action_confirmation(self) -> None:
        decision = PolicyEngine().evaluate(
            ActionPlan(
                plan_name="medium-overall-risk",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.SHOW_TASKS,
                        target="today",
                        risk_level=RiskLevel.LOW,
                        reason="Display tasks.",
                    )
                ],
            ),
            planner_risk_guess=RiskLevel.MEDIUM,
        )

        self.assertTrue(decision.approved)
        self.assertEqual(decision.risk_level, RiskLevel.MEDIUM)
        self.assertFalse(decision.requires_user_confirmation)
        self.assertEqual(decision.issues, [])

    def test_medium_risk_action_requires_action_level_confirmation(self) -> None:
        decision = PolicyEngine().evaluate(
            ActionPlan(
                plan_name="medium-action-risk",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.OPEN_FOLDER,
                        target="Desktop",
                        risk_level=RiskLevel.MEDIUM,
                        reason="Open a sensitive folder.",
                    )
                ],
            )
        )

        self.assertTrue(decision.approved)
        self.assertTrue(decision.requires_user_confirmation)
        self.assertEqual(len(decision.action_decisions), 1)
        self.assertTrue(decision.action_decisions[0].requires_confirmation)

    def test_planner_high_risk_is_not_lowered_by_low_risk_steps(self) -> None:
        decision = PolicyEngine().evaluate(
            ActionPlan(
                plan_name="high-overall-risk",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.OPEN_FOLDER,
                        target="Desktop",
                        risk_level=RiskLevel.LOW,
                        reason="Inspect files before cleanup.",
                    )
                ],
            ),
            planner_risk_guess=RiskLevel.HIGH,
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.risk_level, RiskLevel.HIGH)
        self.assertTrue(decision.requires_user_confirmation)
        self.assertIn("PLANNER_RISK_ELEVATED", {issue.code for issue in decision.issues})
        self.assertIn("RISK_TOO_HIGH", {issue.code for issue in decision.issues})


if __name__ == "__main__":
    unittest.main()
