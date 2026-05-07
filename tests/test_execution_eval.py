from __future__ import annotations

import argparse
import unittest

from desktop_assistant.adapters.fake import FakeContextProvider, FakeReviewer
from desktop_assistant.core.orchestrator import WorkflowOrchestrator
from desktop_assistant.core.policy import PolicyEngine
from desktop_assistant.models import (
    ActionPlan,
    ActionStep,
    ActionType,
    ContextSnapshot,
    ExecutionStatus,
    ExecutionStepResult,
    PlannerResult,
    RiskLevel,
)
from desktop_assistant.storage.in_memory import InMemoryStorage
from desktop_assistant.tools.execution_eval import (
    ExecutionCase,
    build_execution_summary,
    run_suite,
    selected_execution_cases,
)
from desktop_assistant.tools.quality_eval import QualityExpectation


class StaticPlanner:
    def __init__(self, step: ActionStep) -> None:
        self.step = step

    def plan(self, request, context: ContextSnapshot) -> PlannerResult:
        return PlannerResult(
            intent_summary="Static plan",
            requires_clarification=False,
            action_plan=ActionPlan(plan_name="static", source="test", steps=[self.step]),
            risk_guess=RiskLevel.LOW,
        )


class StaticExecutor:
    def __init__(self, status: ExecutionStatus, message: str) -> None:
        self.status = status
        self.message = message

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        return ExecutionStepResult(
            step_index=step_index,
            action=action,
            status=self.status,
            message=f"[{trace_id}] {self.message}",
        )


def build_static_orchestrator(step: ActionStep) -> WorkflowOrchestrator:
    return WorkflowOrchestrator(
        planner=StaticPlanner(step),
        reviewer=FakeReviewer(),
        executor=StaticExecutor(ExecutionStatus.SUCCESS, "planning placeholder"),
        context_provider=FakeContextProvider(),
        storage=InMemoryStorage(),
        policy_engine=PolicyEngine(),
    )


def open_app_case() -> ExecutionCase:
    return ExecutionCase(
        case_id="open_cursor_app",
        request="打开 Cursor 应用",
        category="local_app",
        quality_expectation=QualityExpectation(
            expected_action_prefix=("open_app",),
            max_steps=1,
            require_policy_approved=True,
            require_review_approved=True,
            require_planner_clarification=False,
        ),
        verification_action_types=("open_app",),
    )


class ExecutionEvalTests(unittest.TestCase):
    def test_selected_execution_cases_filters_and_appends_planning_only_custom_requests(self) -> None:
        cases = selected_execution_cases(["open_current_project"], ["临时打开一个工具"])

        self.assertEqual([case.case_id for case in cases], ["open_current_project", "custom_1"])
        self.assertTrue(cases[0].allow_execution)
        self.assertFalse(cases[1].allow_execution)

    def test_run_execution_case_passes_when_app_launch_is_verified(self) -> None:
        from desktop_assistant.tools.execution_eval import run_execution_case

        orchestrator = build_static_orchestrator(
            ActionStep(action_type=ActionType.OPEN_APP, target="Cursor", risk_level=RiskLevel.LOW)
        )

        result = run_execution_case(
            orchestrator,
            open_app_case(),
            client=None,
            executor_factory=lambda: StaticExecutor(
                ExecutionStatus.SUCCESS,
                "Launched and verified app Cursor: C:/Users/AppData/Cursor.exe",
            ),
        )

        self.assertTrue(result["planning_ok"])
        self.assertTrue(result["execution_attempted"])
        self.assertTrue(result["execution_ok"])
        self.assertTrue(result["verification_ok"])
        self.assertTrue(result["full_ok"])

    def test_run_execution_case_marks_unverified_app_launch_separately(self) -> None:
        from desktop_assistant.tools.execution_eval import run_execution_case

        orchestrator = build_static_orchestrator(
            ActionStep(action_type=ActionType.OPEN_APP, target="Cursor", risk_level=RiskLevel.LOW)
        )

        result = run_execution_case(
            orchestrator,
            open_app_case(),
            client=None,
            executor_factory=lambda: StaticExecutor(
                ExecutionStatus.SUCCESS,
                "Launched app Cursor. Window verification is unavailable.",
            ),
        )

        self.assertTrue(result["execution_ok"])
        self.assertFalse(result["verification_ok"])
        self.assertFalse(result["full_ok"])

    def test_run_execution_case_skips_execution_when_planning_fails(self) -> None:
        from desktop_assistant.tools.execution_eval import run_execution_case

        orchestrator = build_static_orchestrator(
            ActionStep(action_type=ActionType.OPEN_URL, target="https://example.com", risk_level=RiskLevel.LOW)
        )

        result = run_execution_case(
            orchestrator,
            open_app_case(),
            client=None,
            executor_factory=lambda: StaticExecutor(
                ExecutionStatus.SUCCESS,
                "This should not run.",
            ),
        )

        self.assertFalse(result["planning_ok"])
        self.assertFalse(result["execution_attempted"])
        self.assertEqual(result["execution_skip_reason"], "planning_failed")

    def test_build_execution_summary_counts_split_outcomes(self) -> None:
        summary = build_execution_summary(
            [
                {
                    "case_id": "a",
                    "planning_ok": True,
                    "execution_attempted": True,
                    "execution_ok": True,
                    "verification_required": True,
                    "verification_ok": True,
                    "full_ok": True,
                    "ok": True,
                    "fallback_calls": 0,
                },
                {
                    "case_id": "b",
                    "planning_ok": True,
                    "execution_attempted": True,
                    "execution_ok": True,
                    "verification_required": True,
                    "verification_ok": False,
                    "full_ok": False,
                    "ok": True,
                    "fallback_calls": 1,
                },
                {
                    "case_id": "c",
                    "planning_ok": False,
                    "execution_attempted": False,
                    "execution_ok": None,
                    "verification_required": False,
                    "verification_ok": None,
                    "full_ok": False,
                    "ok": False,
                    "fallback_calls": 0,
                },
            ]
        )

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["planning_passed"], 2)
        self.assertEqual(summary["execution_attempted"], 2)
        self.assertEqual(summary["execution_passed"], 2)
        self.assertEqual(summary["verification_required"], 2)
        self.assertEqual(summary["verification_passed"], 1)
        self.assertEqual(summary["full_passed"], 1)
        self.assertEqual(summary["full_failed"], 2)
        self.assertEqual(summary["failed_case_ids"], ["b", "c"])

    def test_run_suite_can_use_injected_executor_for_safe_fake_execution(self) -> None:
        args = argparse.Namespace(
            ai_backend="fake",
            provider_config_path=None,
            timeout=180.0,
            max_retries=2,
            retry_backoff_seconds=0.0,
            case=["open_current_project"],
            request=[],
            output=None,
            indent=2,
            confirm_execute=True,
        )

        output = run_suite(
            args,
            executor_factory=lambda: StaticExecutor(
                ExecutionStatus.SUCCESS,
                "Opened project/folder: D:/Cursor_project/4_interesting",
            ),
        )

        self.assertEqual(output["summary"]["total"], 1)
        self.assertEqual(output["summary"]["full_failed"], 0)
        self.assertTrue(output["results"][0]["execution_ok"])
        self.assertIsNone(output["results"][0]["verification_ok"])


if __name__ == "__main__":
    unittest.main()
