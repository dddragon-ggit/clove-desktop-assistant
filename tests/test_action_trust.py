from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from desktop_assistant.action_trust import ActionTrustStore, action_trust_key
from desktop_assistant.core.policy import PolicyEngine
from desktop_assistant.models import ActionPlan, ActionStep, ActionType, RiskLevel
from desktop_assistant.storage.recovery_events import RecoveryEventStore


class ActionTrustTests(unittest.TestCase):
    def _path(self) -> Path:
        base = Path.cwd() / "runtime" / "test_action_trust"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{uuid4().hex}.json"

    def test_trust_key_is_stable_for_same_action(self) -> None:
        action = ActionStep(
            action_type=ActionType.OPEN_FOLDER,
            target="Desktop",
            params={"x": 1},
            risk_level=RiskLevel.MEDIUM,
        )

        self.assertEqual(action_trust_key(action), action_trust_key(action.model_copy(deep=True)))

    def test_policy_uses_action_level_whitelist_for_medium_risk_action(self) -> None:
        action = ActionStep(
            action_type=ActionType.OPEN_FOLDER,
            target="Desktop",
            risk_level=RiskLevel.MEDIUM,
            reason="Open a folder.",
        )
        path = self._path()
        store = ActionTrustStore(path)
        try:
            store.trust_action(action, RiskLevel.MEDIUM)
            decision = PolicyEngine(trusted_action_keys=store.trusted_keys()).evaluate(
                ActionPlan(plan_name="trusted", source="test", steps=[action])
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertTrue(decision.approved)
        self.assertFalse(decision.requires_user_confirmation)
        self.assertEqual(len(decision.action_decisions), 1)
        self.assertTrue(decision.action_decisions[0].whitelisted)

    def test_delete_revokes_trusted_action(self) -> None:
        action = ActionStep(
            action_type=ActionType.OPEN_FOLDER,
            target="Desktop",
            risk_level=RiskLevel.MEDIUM,
        )
        path = self._path()
        store = ActionTrustStore(path)
        try:
            rule = store.trust_action(action, RiskLevel.MEDIUM)
            deleted = store.delete(rule.key)
            keys = store.trusted_keys()
        finally:
            if path.exists():
                path.unlink()

        self.assertTrue(deleted)
        self.assertNotIn(action_trust_key(action), keys)

    def test_load_quarantines_corrupted_whitelist_and_records_recovery(self) -> None:
        path = self._path()
        recovery_path = path.parent / f"{path.stem}_recovery.json"
        path.write_text("{not json", encoding="utf-8")
        store = ActionTrustStore(path)
        try:
            from unittest.mock import patch

            with patch(
                "desktop_assistant.storage.recovery_events.default_recovery_event_path",
                return_value=recovery_path,
            ):
                rules = store.load()
            latest = RecoveryEventStore(recovery_path).latest(max_age_hours=9999)
        finally:
            for item in path.parent.glob(f"{path.name}.corrupt*"):
                item.unlink(missing_ok=True)
            if path.exists():
                path.unlink()
            if recovery_path.exists():
                recovery_path.unlink()

        self.assertEqual(rules, [])
        self.assertIsNotNone(latest)
        self.assertEqual(latest.source, "action_trust_store")


if __name__ == "__main__":
    unittest.main()
