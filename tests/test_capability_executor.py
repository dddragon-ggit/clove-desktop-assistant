from __future__ import annotations

import unittest

from desktop_assistant.capability_executor import CapabilityExecutor
from desktop_assistant.models import ActionStep, ActionType, ExecutionStatus, ExecutionStepResult, RiskLevel


class RecordingHandler:
    action_type = ActionType.OPEN_URL

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        self.calls.append(action.target)
        return ExecutionStepResult(
            step_index=step_index,
            action=action,
            status=ExecutionStatus.SUCCESS,
            message=f"[{trace_id}] handled {action.target}",
        )


class RaisingHandler:
    action_type = ActionType.OPEN_URL

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        raise OSError("boom")


class CapabilityExecutorTests(unittest.TestCase):
    def test_dispatches_to_registered_handler(self) -> None:
        handler = RecordingHandler()
        executor = CapabilityExecutor([handler])
        action = ActionStep(
            action_type=ActionType.OPEN_URL,
            target="https://example.com",
            risk_level=RiskLevel.LOW,
        )

        result = executor.execute(action, step_index=2, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.step_index, 2)
        self.assertEqual(handler.calls, ["https://example.com"])

    def test_validation_blocks_before_handler_runs(self) -> None:
        handler = RecordingHandler()
        executor = CapabilityExecutor([handler])
        action = ActionStep(
            action_type=ActionType.OPEN_URL,
            target="file:///C:/secret.txt",
            risk_level=RiskLevel.LOW,
        )

        result = executor.execute(action, step_index=0, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("URL_SCHEME_NOT_ALLOWED", result.message)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "CAPABILITY_VALIDATION_FAILED")
        self.assertEqual(result.diagnosis.details["issues"][0]["code"], "URL_SCHEME_NOT_ALLOWED")
        self.assertEqual(handler.calls, [])

    def test_missing_handler_skips_enabled_capability(self) -> None:
        executor = CapabilityExecutor([])
        action = ActionStep(
            action_type=ActionType.OPEN_URL,
            target="https://example.com",
            risk_level=RiskLevel.LOW,
        )

        result = executor.execute(action, step_index=0, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.SKIPPED)
        self.assertIn("No handler is registered", result.message)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "HANDLER_NOT_REGISTERED")
        self.assertEqual(result.diagnosis.details["action_type"], "open_url")

    def test_handler_os_error_becomes_failed_result(self) -> None:
        executor = CapabilityExecutor([RaisingHandler()])
        action = ActionStep(
            action_type=ActionType.OPEN_URL,
            target="https://example.com",
            risk_level=RiskLevel.LOW,
        )

        result = executor.execute(action, step_index=0, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("OS error", result.message)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "OS_ERROR")


if __name__ == "__main__":
    unittest.main()
