from __future__ import annotations

import unittest

from desktop_assistant.adapters.fake import FakeContextProvider, FakeExecutor, FakePlanner, FakeReviewer
from desktop_assistant.capabilities import CapabilityRegistry
from desktop_assistant.core.orchestrator import WorkflowOrchestrator
from desktop_assistant.core.policy import PolicyEngine
from desktop_assistant.models import (
    ExecutionDiagnosis,
    ExecutionStatus,
    ExecutionStepResult,
    RunMode,
    WorkflowRequest,
)
from desktop_assistant.storage.in_memory import InMemoryStorage
from desktop_assistant.storage.recovery_events import RecoveryEventRecord
from desktop_assistant.tools.capability_debug import (
    build_capability_debug_report,
    format_capability_debug_report,
)
from desktop_assistant.ui.view_model import capability_detail_to_plain_text, summarize_capability_registry


def build_orchestrator(storage: InMemoryStorage) -> WorkflowOrchestrator:
    return WorkflowOrchestrator(
        planner=FakePlanner(),
        reviewer=FakeReviewer(),
        executor=FakeExecutor(),
        context_provider=FakeContextProvider(),
        storage=storage,
        policy_engine=PolicyEngine(),
    )


class CapabilityDebugTests(unittest.TestCase):
    def test_report_marks_missing_handlers_and_recent_failures(self) -> None:
        storage = InMemoryStorage()
        orchestrator = build_orchestrator(storage)
        trace = orchestrator.run(
            WorkflowRequest(user_request="开始做周报", run_mode=RunMode.DRY_RUN)
        )
        failed_action = trace.planner_result.action_plan.steps[0]
        trace.step_results.append(
            ExecutionStepResult(
                step_index=0,
                action=failed_action,
                status=ExecutionStatus.FAILED,
                message="App not found.",
                diagnosis=ExecutionDiagnosis(
                    code="APP_NOT_IN_INVENTORY",
                    message="App not found.",
                    details={"target": failed_action.target},
                    remedy="Refresh app_inventory.json.",
                ),
            )
        )
        storage.save_trace(trace)

        report = build_capability_debug_report(
            registry=CapabilityRegistry.default(),
            storage=storage,
            catalog_path="runtime/data/capabilities.json",
            available_handler_names={"simulated", "windows.open_url"},
        )
        text = format_capability_debug_report(report)
        open_app = next(item for item in report["capabilities"] if item["action_type"] == "open_app")

        self.assertEqual(open_app["handler_status"], "missing")
        self.assertEqual(open_app["recent_failure_count"], 1)
        self.assertEqual(open_app["recent_failure_code"], "APP_NOT_IN_INVENTORY")
        self.assertGreaterEqual(report["missing_handlers"], 1)
        self.assertIn("Capability Debug Report", text)
        self.assertIn("APP_NOT_IN_INVENTORY", text)

    def test_report_includes_recent_recovery_events(self) -> None:
        report = build_capability_debug_report(
            registry=CapabilityRegistry.default(),
            recovery_store=_StaticRecoveryStore(
                [
                    RecoveryEventRecord(
                        id="recovery-1",
                        created_at="2026-05-02T08:30:00+00:00",
                        source="todo_store",
                        category="todo_store_corrupted",
                        path="D:/runtime/data/todos.json",
                        quarantined_path="D:/runtime/data/todos.json.corrupt",
                        reason="Todo JSON is unreadable.",
                    )
                ]
            ),
            available_handler_names={"simulated"},
        )
        text = format_capability_debug_report(report)

        self.assertEqual(report["recovery_event_count"], 1)
        self.assertEqual(report["recent_recovery_events"][0]["source"], "todo_store")
        self.assertIn("Recent recovery events", text)
        self.assertIn("todos.json.corrupt", text)

    def test_capability_summary_has_product_health_and_risk_explanation(self) -> None:
        summaries = summarize_capability_registry(
            CapabilityRegistry.default(),
            available_handler_names={"simulated"},
        )

        open_app = next(summary for summary in summaries if summary.action_type == "open_app")
        detail = capability_detail_to_plain_text(open_app)

        self.assertIn(open_app.health_label, {"需要接 handler", "可测试", "最近有失败", "已停用"})
        self.assertIn("风险说明", detail)
        self.assertIn("调试建议", detail)
        self.assertIn("能力：打开应用", detail)


if __name__ == "__main__":
    unittest.main()


class _StaticRecoveryStore:
    def __init__(self, records) -> None:
        self._records = records

    def load(self):
        return list(self._records)
