from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import uuid4

from desktop_assistant.capability_store import CapabilityStore
from desktop_assistant.models import ActionType, RiskLevel
from desktop_assistant.storage.recovery_events import RecoveryEventStore


class CapabilityStoreTests(unittest.TestCase):
    def _catalog_path(self) -> Path:
        base = Path.cwd() / "runtime" / "test_capability_catalog"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{uuid4().hex}.json"

    def test_ensure_writes_default_catalog(self) -> None:
        path = self._catalog_path()
        store = CapabilityStore(path=path)
        try:
            registry = store.ensure()
            payload = json.loads(path.read_text(encoding="utf-8"))
        finally:
            if path.exists():
                path.unlink()

        self.assertIn("open_app", registry.allowed_action_values())
        self.assertIn("answer_query", registry.allowed_action_values())
        self.assertEqual(payload["schema_version"], 1)
        self.assertTrue(any(item["action_type"] == "open_app" for item in payload["capabilities"]))
        self.assertTrue(any(item["action_type"] == "answer_query" for item in payload["capabilities"]))

    def test_load_merges_catalog_over_builtin_defaults(self) -> None:
        path = self._catalog_path()
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "capabilities": [
                        {
                            "action_type": "open_url",
                            "execution_mode": "disabled",
                            "default_risk": "medium",
                            "planner_guidance": ["Temporarily disabled for test."],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        try:
            registry = CapabilityStore(path=path).load()
        finally:
            if path.exists():
                path.unlink()

        open_url = registry.get(ActionType.OPEN_URL)
        self.assertIsNotNone(open_url)
        self.assertEqual(open_url.execution_mode, "disabled")
        self.assertEqual(open_url.default_risk, RiskLevel.MEDIUM)
        self.assertIn("open_app", registry.allowed_action_values())
        self.assertNotIn("open_url", registry.allowed_action_values())

    def test_ensure_recovers_corrupt_catalog(self) -> None:
        path = self._catalog_path()
        path.write_text("{not json", encoding="utf-8")
        try:
            registry = CapabilityStore(path=path).ensure()
            payload = json.loads(path.read_text(encoding="utf-8"))
        finally:
            if path.exists():
                path.unlink()

        self.assertIn("open_url", registry.allowed_action_values())
        self.assertEqual(payload["schema_version"], 1)

    def test_missing_real_handler_disables_matching_capability(self) -> None:
        path = self._catalog_path()
        store = CapabilityStore(path=path)
        try:
            registry = store.ensure(available_handler_names={"simulated", "windows.open_url"})
        finally:
            if path.exists():
                path.unlink()

        self.assertIn("open_url", registry.allowed_action_values())
        self.assertNotIn("open_app", registry.allowed_action_values())
        open_app = registry.get(ActionType.OPEN_APP)
        self.assertIsNotNone(open_app)
        self.assertEqual(open_app.execution_mode, "disabled")

    def test_update_capability_persists_user_edit(self) -> None:
        path = self._catalog_path()
        store = CapabilityStore(path=path)
        try:
            registry = store.update_capability(
                ActionType.ANSWER_QUERY,
                execution_mode="disabled",
                default_risk="medium",
                description="Temporarily disabled in tests.",
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
        finally:
            if path.exists():
                path.unlink()

        answer_query = registry.get(ActionType.ANSWER_QUERY)
        self.assertIsNotNone(answer_query)
        self.assertEqual(answer_query.execution_mode, "disabled")
        self.assertEqual(answer_query.default_risk, RiskLevel.MEDIUM)
        saved = next(item for item in payload["capabilities"] if item["action_type"] == "answer_query")
        self.assertEqual(saved["description"], "Temporarily disabled in tests.")

    def test_load_quarantines_invalid_catalog_and_records_recovery(self) -> None:
        path = self._catalog_path()
        recovery_path = path.parent / f"{path.stem}_recovery.json"
        path.write_text("{not json", encoding="utf-8")
        try:
            from unittest.mock import patch

            with patch(
                "desktop_assistant.storage.recovery_events.default_recovery_event_path",
                return_value=recovery_path,
            ):
                with self.assertRaises(ValueError):
                    CapabilityStore(path=path).load()
            latest = RecoveryEventStore(recovery_path).latest(max_age_hours=9999)
        finally:
            for item in path.parent.glob(f"{path.name}.corrupt*"):
                item.unlink(missing_ok=True)
            if path.exists():
                path.unlink()
            if recovery_path.exists():
                recovery_path.unlink()

        self.assertIsNotNone(latest)
        self.assertEqual(latest.source, "capability_store")


if __name__ == "__main__":
    unittest.main()
