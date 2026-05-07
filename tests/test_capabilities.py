from __future__ import annotations

import unittest

from desktop_assistant.capabilities import CapabilityRegistry
from desktop_assistant.core.policy import PolicyEngine
from desktop_assistant.models import ActionPlan, ActionStep, ActionType, RiskLevel


class CapabilityRegistryTests(unittest.TestCase):
    def test_default_registry_exposes_enabled_capabilities_to_planner(self) -> None:
        registry = CapabilityRegistry.default()

        allowed_actions = registry.allowed_action_values()
        prompt_summary = registry.prompt_summary()
        provider_payload = registry.to_provider_payload()

        self.assertIn("open_app", allowed_actions)
        self.assertIn("focus_app", allowed_actions)
        self.assertIn("open_url", allowed_actions)
        self.assertIn("open_project", allowed_actions)
        self.assertIn("list_windows", allowed_actions)
        self.assertIn("focus_window", allowed_actions)
        self.assertIn("minimize_window", allowed_actions)
        self.assertIn("maximize_window", allowed_actions)
        self.assertIn("restore_window", allowed_actions)
        self.assertIn("close_window", allowed_actions)
        self.assertIn("answer_query", allowed_actions)
        self.assertNotIn("restore_workspace", allowed_actions)
        self.assertIn("open_app", prompt_summary)
        self.assertIn("list_windows", prompt_summary)
        self.assertIn("close_window", prompt_summary)
        self.assertIn("answer_query", prompt_summary)
        self.assertTrue(all(item["execution_mode"] != "disabled" for item in provider_payload))

    def test_policy_rejects_non_http_open_url_before_execution(self) -> None:
        decision = PolicyEngine().evaluate(
            ActionPlan(
                plan_name="bad-url",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.OPEN_URL,
                        target="file:///C:/secret.txt",
                        risk_level=RiskLevel.LOW,
                        reason="Should not open file URLs through the browser capability.",
                    )
                ],
            )
        )

        self.assertFalse(decision.approved)
        self.assertIn("URL_SCHEME_NOT_ALLOWED", {issue.code for issue in decision.issues})

    def test_policy_rejects_shell_like_app_targets(self) -> None:
        decision = PolicyEngine().evaluate(
            ActionPlan(
                plan_name="blocked-shell",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.OPEN_APP,
                        target="PowerShell",
                        risk_level=RiskLevel.LOW,
                        reason="Shell-like app launch is outside the current safety envelope.",
                    )
                ],
            )
        )

        self.assertFalse(decision.approved)
        self.assertIn("APP_LAUNCH_BLOCKED", {issue.code for issue in decision.issues})

    def test_disabled_capability_is_blocked_even_if_explicitly_allowed(self) -> None:
        decision = PolicyEngine(allowed_actions=[ActionType.RESTORE_WORKSPACE]).evaluate(
            ActionPlan(
                plan_name="disabled-capability",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.RESTORE_WORKSPACE,
                        target="writing",
                        risk_level=RiskLevel.LOW,
                        reason="Workspace restoration is not implemented yet.",
                    )
                ],
            )
        )

        self.assertFalse(decision.approved)
        self.assertEqual(decision.risk_level, RiskLevel.MEDIUM)
        self.assertIn("CAPABILITY_DISABLED", {issue.code for issue in decision.issues})

    def test_close_window_requires_action_level_confirmation(self) -> None:
        decision = PolicyEngine().evaluate(
            ActionPlan(
                plan_name="close-window",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.CLOSE_WINDOW,
                        target="Untitled - Notepad",
                        risk_level=RiskLevel.LOW,
                        reason="User explicitly asked to close the window.",
                    )
                ],
            )
        )

        self.assertTrue(decision.approved)
        self.assertEqual(decision.risk_level, RiskLevel.MEDIUM)
        self.assertTrue(decision.requires_user_confirmation)
        self.assertTrue(decision.action_decisions[0].requires_confirmation)


if __name__ == "__main__":
    unittest.main()
