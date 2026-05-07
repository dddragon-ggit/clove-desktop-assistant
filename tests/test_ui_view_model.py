from __future__ import annotations

import unittest

from desktop_assistant.adapters.fake import FakeContextProvider, FakeExecutor, FakePlanner, FakeReviewer
from desktop_assistant.capabilities import CapabilityRegistry
from desktop_assistant.core.orchestrator import WorkflowOrchestrator
from desktop_assistant.core.policy import PolicyEngine
from desktop_assistant.models import (
    ActionPlan,
    DebugRunRecord,
    ExecutionDiagnosis,
    ExecutionStatus,
    ExecutionStepResult,
    PlannerResult,
    PolicyDecision,
    PolicyIssue,
    RecentTraceRecord,
    ReviewResult,
    RiskLevel,
    RunMode,
    WorkflowTrace,
    WorkflowRequest,
    WorkflowStatus,
)
from desktop_assistant.storage.in_memory import InMemoryStorage
from desktop_assistant.storage.recovery_events import RecoveryEventRecord
from desktop_assistant.ui.view_model import (
    capability_detail_to_plain_text,
    capability_label,
    debug_run_label,
    summarize_debug_run,
    summarize_capability_registry,
    recent_trace_label,
    recovery_event_detail_text,
    recovery_event_label,
    summarize_recent_trace,
    summarize_recovery_event,
    summarize_trace,
    summarize_window_metadata,
    summary_to_plain_text,
    window_detail_to_plain_text,
    window_row_values,
    window_state_label,
)


def build_orchestrator() -> WorkflowOrchestrator:
    return WorkflowOrchestrator(
        planner=FakePlanner(),
        reviewer=FakeReviewer(),
        executor=FakeExecutor(),
        context_provider=FakeContextProvider(),
        storage=InMemoryStorage(),
        policy_engine=PolicyEngine(),
    )


class UIViewModelTests(unittest.TestCase):
    def test_summarize_trace_extracts_status_risk_and_steps(self) -> None:
        trace = build_orchestrator().run(
            WorkflowRequest(user_request="开始做周报", run_mode=RunMode.DRY_RUN)
        )

        summary = summarize_trace(trace)

        self.assertEqual(summary.status, "dry_run_ready")
        self.assertEqual(summary.plan_name, "weekly-report-setup")
        self.assertEqual(summary.plan_source, "fake_planner")
        self.assertIn("prepare_seconds", summary.timings)
        self.assertEqual(summary.policy_risk, "medium")
        self.assertFalse(summary.policy_requires_confirmation)
        self.assertFalse(summary.requires_confirmation)
        self.assertTrue(summary.can_run_once)
        self.assertEqual(summary.decision_state, "ready")
        self.assertEqual(len(summary.steps), 3)
        self.assertEqual(summary.steps[0].action_type, "open_app")
        self.assertEqual(summary.steps[0].target, "Notion")

    def test_summarize_trace_includes_execution_results(self) -> None:
        trace = build_orchestrator().run(
            WorkflowRequest(user_request="write setup", run_mode=RunMode.NORMAL)
        )

        summary = summarize_trace(trace)

        self.assertEqual(summary.status, "completed")
        self.assertEqual(summary.decision_state, "executed")
        self.assertFalse(summary.can_run_once)
        self.assertEqual(summary.steps[0].execution_status, "success")
        self.assertIn("Simulated execution", summary.steps[0].execution_message or "")
        self.assertIsNotNone(summary.steps[0].elapsed_seconds)

    def test_summary_to_plain_text_includes_core_sections(self) -> None:
        trace = build_orchestrator().run(
            WorkflowRequest(user_request="开始写作", run_mode=RunMode.DRY_RUN)
        )
        summary = summarize_trace(trace)

        text = summary_to_plain_text(summary)

        self.assertIn("追踪:", text)
        self.assertIn("策略风险:", text)
        self.assertIn("计划来源:", text)
        self.assertIn("审查:", text)
        self.assertIn("决策状态:", text)
        self.assertIn("计划动作:", text)
        self.assertIn("打开应用 -> Obsidian", text)
        self.assertNotIn("Policy risk:", text)
        self.assertNotIn("open_app -> Obsidian", text)

    def test_blocked_trace_summary_disables_run_once(self) -> None:
        trace = build_orchestrator().run(
            WorkflowRequest(user_request="帮我运行 PowerShell 脚本清理电脑", run_mode=RunMode.DRY_RUN)
        )
        trace.policy_decision.approved = False

        summary = summarize_trace(trace)

        self.assertEqual(summary.decision_state, "blocked")
        self.assertFalse(summary.can_run_once)

    def test_stopped_trace_summary_disables_run_once(self) -> None:
        trace = build_orchestrator().run(
            WorkflowRequest(user_request="write setup", run_mode=RunMode.DRY_RUN)
        )
        trace.status = WorkflowStatus.STOPPED

        summary = summarize_trace(trace)

        self.assertEqual(summary.decision_state, "stopped")
        self.assertFalse(summary.can_run_once)

    def test_prepare_failure_summary_is_structured_and_not_runnable(self) -> None:
        trace = WorkflowTrace(
            trace_id="trace-prepare-failed",
            request=WorkflowRequest(user_request="打开 QQ", run_mode=RunMode.DRY_RUN),
            context=FakeContextProvider().get_context(),
            planner_result=PlannerResult(
                intent_summary="准备阶段失败，未能生成可执行计划。",
                action_plan=ActionPlan(plan_name="prepare-failed", source="prepare_error:planner", steps=[]),
                risk_guess=RiskLevel.MEDIUM,
                reasoning_summary="planner failed",
            ),
            policy_decision=PolicyDecision(
                approved=False,
                risk_level=RiskLevel.MEDIUM,
                requires_user_confirmation=False,
                issues=[PolicyIssue(code="PREPARE_PLANNER_FAILED", message="规划失败：RuntimeError: boom")],
                action_decisions=[],
            ),
            review_result=ReviewResult(
                approved=False,
                risk_level=RiskLevel.MEDIUM,
                needs_user_confirmation=False,
                review_summary="规划失败：RuntimeError: boom",
                issues=["规划失败：RuntimeError: boom"],
                rejection_reason="规划失败：RuntimeError: boom",
            ),
            prepare_error=ExecutionDiagnosis(
                code="PREPARE_PLANNER_FAILED",
                message="规划失败：RuntimeError: boom",
                details={"stage": "planner", "error_type": "RuntimeError", "error": "boom"},
                remedy="请检查规划器实现、模型配置或提示词输入。",
            ),
            status=WorkflowStatus.FAILED,
        )

        summary = summarize_trace(trace)
        text = summary_to_plain_text(summary)

        self.assertEqual(summary.decision_state, "failed")
        self.assertFalse(summary.can_run_once)
        self.assertEqual(summary.prepare_error_code, "PREPARE_PLANNER_FAILED")
        self.assertEqual(summary.prepare_error_stage, "planner")
        self.assertIn("准备失败:", text)
        self.assertIn("阶段: 规划", text)
        self.assertIn("代码: PREPARE_PLANNER_FAILED", text)
        self.assertIn("建议:", text)

    def test_recent_trace_summary_and_label(self) -> None:
        trace = build_orchestrator().run(
            WorkflowRequest(user_request="做项目复盘并打开复盘资料", run_mode=RunMode.DRY_RUN)
        )
        record = RecentTraceRecord(
            trace_id=trace.trace_id,
            status=trace.status,
            created_at="2026-04-27T12:00:00+00:00",
            updated_at="2026-04-27T12:05:00+00:00",
            trace=trace,
        )

        summary = summarize_recent_trace(record)
        label = recent_trace_label(summary)

        self.assertEqual(summary.trace_id, trace.trace_id)
        self.assertEqual(summary.status, "dry_run_ready")
        self.assertEqual(summary.risk_level, "low")
        self.assertIn("04-27 12:05", label)
        self.assertIn(trace.trace_id[:8], label)

    def test_debug_run_summary_and_label_include_snapshot_details(self) -> None:
        trace = build_orchestrator().run(
            WorkflowRequest(user_request="开始做周报", run_mode=RunMode.DRY_RUN)
        )
        trace.step_results.append(
            ExecutionStepResult(
                step_index=0,
                action=trace.planner_result.action_plan.steps[0],
                status=ExecutionStatus.FAILED,
                message="App not found.",
                diagnosis=ExecutionDiagnosis(
                    code="APP_NOT_IN_INVENTORY",
                    message="App not found.",
                    details={"target": "Notion"},
                    remedy="Refresh app_inventory.json.",
                ),
            )
        )
        debug_run = DebugRunRecord(
            id="debug-1234567890",
            trace_id=trace.trace_id,
            run_mode=RunMode.DRY_RUN,
            trigger_source=trace.request.user_request,
            input_json=trace.request.model_dump(mode="json"),
            current_step=0,
            status=trace.status,
            snapshot_json=trace.model_dump(mode="json"),
            created_at="2026-04-27T12:06:00+00:00",
            updated_at="2026-04-27T12:06:00+00:00",
        )

        summary = summarize_debug_run(debug_run)
        label = debug_run_label(summary)

        self.assertEqual(summary.id, "debug-1234567890")
        self.assertEqual(summary.run_mode, "dry_run")
        self.assertIn("04-27 12:06", label)
        self.assertIn("debug-12", label)
        self.assertIn("Planner", summary.snapshot_text)
        self.assertIn("Policy", summary.snapshot_text)
        self.assertIn("Step results", summary.snapshot_text)
        self.assertIn("Failure code: APP_NOT_IN_INVENTORY", summary.snapshot_text)
        self.assertIn("Refresh app_inventory.json.", summary.snapshot_text)

    def test_debug_snapshot_includes_prepare_error_section(self) -> None:
        trace = WorkflowTrace(
            trace_id="trace-prepare-failed",
            request=WorkflowRequest(user_request="打开 QQ", run_mode=RunMode.DRY_RUN),
            context=FakeContextProvider().get_context(),
            planner_result=PlannerResult(
                intent_summary="准备阶段失败，未能生成可执行计划。",
                action_plan=ActionPlan(plan_name="prepare-failed", source="prepare_error:planner", steps=[]),
                risk_guess=RiskLevel.MEDIUM,
            ),
            policy_decision=PolicyDecision(
                approved=False,
                risk_level=RiskLevel.MEDIUM,
                requires_user_confirmation=False,
                issues=[PolicyIssue(code="PREPARE_PLANNER_FAILED", message="规划失败：RuntimeError: boom")],
                action_decisions=[],
            ),
            review_result=ReviewResult(
                approved=False,
                risk_level=RiskLevel.MEDIUM,
                needs_user_confirmation=False,
                review_summary="规划失败：RuntimeError: boom",
                issues=["规划失败：RuntimeError: boom"],
                rejection_reason="规划失败：RuntimeError: boom",
            ),
            prepare_error=ExecutionDiagnosis(
                code="PREPARE_PLANNER_FAILED",
                message="规划失败：RuntimeError: boom",
                details={"stage": "planner", "error_type": "RuntimeError", "error": "boom"},
                remedy="请检查规划器实现、模型配置或提示词输入。",
            ),
            status=WorkflowStatus.FAILED,
        )
        debug_run = DebugRunRecord(
            id="debug-prepare-failed",
            trace_id=trace.trace_id,
            run_mode=RunMode.DRY_RUN,
            trigger_source=trace.request.user_request,
            input_json=trace.request.model_dump(mode="json"),
            current_step=0,
            status=trace.status,
            snapshot_json=trace.model_dump(mode="json"),
            created_at="2026-04-27T12:06:00+00:00",
            updated_at="2026-04-27T12:06:00+00:00",
        )

        summary = summarize_debug_run(debug_run)

        self.assertIn("Prepare error", summary.snapshot_text)
        self.assertIn("PREPARE_PLANNER_FAILED", summary.snapshot_text)
        self.assertIn("RuntimeError: boom", summary.snapshot_text)

    def test_recovery_event_summary_and_detail_text(self) -> None:
        record = RecoveryEventRecord(
            id="recovery-1",
            created_at="2026-05-02T08:30:00+00:00",
            source="todo_store",
            category="todo_store_corrupted",
            path="D:/runtime/data/todos.json",
            quarantined_path="D:/runtime/data/todos.json.corrupt",
            reason="Todo JSON is unreadable.",
        )

        summary = summarize_recovery_event(record)
        label = recovery_event_label(summary)
        detail = recovery_event_detail_text(summary)

        self.assertIn("05-02 08:30", label)
        self.assertIn("待办", label)
        self.assertIn("todo_store_corrupted", label)
        self.assertIn("恢复时间：2026-05-02T08:30:00+00:00", detail)
        self.assertIn("隔离文件：D:/runtime/data/todos.json.corrupt", detail)
        self.assertIn("Todo JSON is unreadable.", detail)

    def test_capability_summary_and_detail_text(self) -> None:
        registry = CapabilityRegistry.default()

        summaries = summarize_capability_registry(
            registry,
            catalog_path="runtime/data/capabilities.json",
            available_handler_names={"simulated", "windows.open_app"},
        )
        open_app = next(summary for summary in summaries if summary.action_type == "open_app")
        label = capability_label(open_app)
        detail = capability_detail_to_plain_text(open_app)

        self.assertIn("打开应用", label)
        self.assertIn("启用", label)
        self.assertIn("可测试", label)
        self.assertIn("能力：打开应用", detail)
        self.assertIn("Handler：windows.open_app", detail)
        self.assertIn("Handler 状态：可用", detail)
        self.assertIn("目标格式", detail)
        self.assertIn("安全规则", detail)

    def test_window_metadata_summary_marks_foreground_and_state(self) -> None:
        summaries = summarize_window_metadata(
            {
                "foreground_window": {"hwnd": "10", "title": "QQ"},
                "windows": [
                    {
                        "hwnd": "10",
                        "title": "QQ",
                        "process_id": "101",
                        "executable_path": "D:/Tencent/QQ.exe",
                        "is_minimized": True,
                    },
                    {
                        "hwnd": 20,
                        "title": "Cursor",
                        "process_id": 202,
                        "executable_path": "D:/Cursor/Cursor.exe",
                        "is_maximized": True,
                    },
                ],
            }
        )

        self.assertEqual(len(summaries), 2)
        self.assertTrue(summaries[0].is_foreground)
        self.assertEqual(window_state_label(summaries[0]), "前台，已最小化")
        self.assertEqual(window_state_label(summaries[1]), "已最大化")
        self.assertEqual(window_row_values(summaries[0])[0], "10")

        detail = window_detail_to_plain_text(summaries[0])

        self.assertIn("窗口：QQ", detail)
        self.assertIn("句柄：10", detail)
        self.assertIn("程序位置：D:/Tencent/QQ.exe", detail)


if __name__ == "__main__":
    unittest.main()
