from __future__ import annotations

import unittest

from desktop_assistant.adapters.fake import FakeContextProvider, FakeExecutor, FakePlanner, FakeReviewer
from desktop_assistant.core.orchestrator import WorkflowOrchestrator
from desktop_assistant.core.policy import PolicyEngine
from desktop_assistant.models import (
    ActionPlan,
    ActionStep,
    ActionType,
    ContextSnapshot,
    ExecutionDiagnosis,
    ExecutionStatus,
    ExecutionStepResult,
    PlannerResult,
    RiskLevel,
    RunMode,
    WorkflowRequest,
    WorkflowStatus,
)
from desktop_assistant.recipes import build_plan_refinement_context
from desktop_assistant.storage.in_memory import InMemoryStorage


def build_orchestrator() -> WorkflowOrchestrator:
    return WorkflowOrchestrator(
        planner=FakePlanner(),
        reviewer=FakeReviewer(),
        executor=FakeExecutor(),
        context_provider=FakeContextProvider(),
        storage=InMemoryStorage(),
        policy_engine=PolicyEngine(),
    )


class RepeatedFailurePlanner:
    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        action = ActionStep(
            action_type=ActionType.OPEN_FOLDER,
            target="missing",
            risk_level=RiskLevel.LOW,
            reason="Deliberately fails.",
        )
        return PlannerResult(
            intent_summary="Repeated failure test",
            action_plan=ActionPlan(
                plan_name="repeat-failure",
                source="test",
                steps=[action, action.model_copy(deep=True), action.model_copy(deep=True)],
            ),
            risk_guess=RiskLevel.LOW,
        )


class AlwaysFailExecutor:
    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        return ExecutionStepResult(
            step_index=step_index,
            action=action,
            status=ExecutionStatus.FAILED,
            message=f"[{trace_id}] failed",
            diagnosis=ExecutionDiagnosis(code="TEST_FAILURE", message="failed"),
        )


class RecoveringPlanner:
    def __init__(self) -> None:
        self.recovery_context_seen = None

    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        if request.recovery_context is not None:
            self.recovery_context_seen = request.recovery_context
            action = ActionStep(
                action_type=ActionType.OPEN_FOLDER,
                target="D:/Recovered",
                risk_level=RiskLevel.LOW,
                reason="Use a corrected folder target after the original target failed.",
            )
            return PlannerResult(
                intent_summary="Recovery plan",
                action_plan=ActionPlan(plan_name="recovered-plan", source="test", steps=[action]),
                risk_guess=RiskLevel.LOW,
                reasoning_summary="Recovered from the failed folder target.",
            )

        action = ActionStep(
            action_type=ActionType.OPEN_FOLDER,
            target="missing",
            risk_level=RiskLevel.LOW,
            reason="Initial target is intentionally missing.",
        )
        return PlannerResult(
            intent_summary="Initial plan",
            action_plan=ActionPlan(plan_name="initial-plan", source="test", steps=[action]),
            risk_guess=RiskLevel.LOW,
        )


class FailMissingExecutor:
    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        if action.target == "missing":
            return ExecutionStepResult(
                step_index=step_index,
                action=action,
                status=ExecutionStatus.FAILED,
                message=f"[{trace_id}] target is missing",
                diagnosis=ExecutionDiagnosis(
                    code="TARGET_NOT_FOUND",
                    message="Target folder was not found.",
                    details={"target": action.target},
                    remedy="Choose another folder target.",
                ),
            )
        return ExecutionStepResult(
            step_index=step_index,
            action=action,
            status=ExecutionStatus.SUCCESS,
            message=f"[{trace_id}] opened {action.target}",
        )


class LocalAppFailurePlanner:
    def __init__(self) -> None:
        self.calls = 0
        self.recovery_context_seen = None

    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        self.calls += 1
        if request.recovery_context is not None:
            self.recovery_context_seen = request.recovery_context
            action = ActionStep(
                action_type=ActionType.FOCUS_WINDOW,
                target="Battle.net",
                risk_level=RiskLevel.LOW,
                reason="Focus the visible launcher window after the app launch produced no direct window match.",
            )
            return PlannerResult(
                intent_summary="Recover Battle.net window",
                action_plan=ActionPlan(plan_name="recover-window", source="test", steps=[action]),
                risk_guess=RiskLevel.LOW,
            )
        action = ActionStep(
            action_type=ActionType.OPEN_APP,
            target="Battle.net",
            risk_level=RiskLevel.LOW,
            reason="Open a local launcher app.",
        )
        return PlannerResult(
            intent_summary="Open Battle.net",
            action_plan=ActionPlan(plan_name="open-app", source="test", steps=[action]),
            risk_guess=RiskLevel.LOW,
        )


class LocalAppLaunchFailExecutor:
    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        if action.action_type == ActionType.FOCUS_WINDOW:
            return ExecutionStepResult(
                step_index=step_index,
                action=action,
                status=ExecutionStatus.SUCCESS,
                message=f"[{trace_id}] focused {action.target}",
            )
        return ExecutionStepResult(
            step_index=step_index,
            action=action,
            status=ExecutionStatus.FAILED,
            message=f"[{trace_id}] process running but no window",
            diagnosis=ExecutionDiagnosis(
                code="APP_PROCESS_RUNNING_NO_WINDOW",
                message="Process was detected but no visible window was found.",
                details={"process": {"process_id": 777}},
                remedy="Open the app from the system tray or retry later.",
            ),
        )


class TerminalRecoveryPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        self.calls += 1
        if request.recovery_context is not None:
            raise AssertionError("Terminal execution failures should stop without model recovery.")
        action = ActionStep(
            action_type=ActionType.LIST_WINDOWS,
            target="visible",
            risk_level=RiskLevel.LOW,
            reason="List windows.",
        )
        return PlannerResult(
            intent_summary="List windows",
            action_plan=ActionPlan(plan_name="list-windows", source="test", steps=[action]),
            risk_guess=RiskLevel.LOW,
        )


class WindowEnumerationFailExecutor:
    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        return ExecutionStepResult(
            step_index=step_index,
            action=action,
            status=ExecutionStatus.FAILED,
            message=f"[{trace_id}] window enumeration failed",
            diagnosis=ExecutionDiagnosis(
                code="WINDOW_ENUMERATION_FAILED",
                message="Window enumeration failed.",
                details={"error": "access denied"},
                remedy="Run in the same interactive desktop session.",
            ),
        )


class RepeatingRecoveryPlanner:
    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        action = ActionStep(
            action_type=ActionType.OPEN_FOLDER,
            target="missing",
            risk_level=RiskLevel.LOW,
            reason="Repeat the same missing folder.",
        )
        return PlannerResult(
            intent_summary="Repeating recovery",
            action_plan=ActionPlan(plan_name="repeat-recovery", source="test", steps=[action]),
            risk_guess=RiskLevel.LOW,
        )


class AppInventoryRecoveryPlanner:
    def __init__(self) -> None:
        self.recovery_context_seen = None

    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        if request.recovery_context is not None:
            self.recovery_context_seen = request.recovery_context
            action = ActionStep(
                action_type=ActionType.OPEN_APP,
                target="Battle.net",
                params={"executable_path": "D:/Battle.net/Battle.net.exe"},
                risk_level=RiskLevel.LOW,
                reason="Use the refreshed app inventory match.",
            )
            return PlannerResult(
                intent_summary="Recovered app target",
                action_plan=ActionPlan(plan_name="recover-app", source="test", steps=[action]),
                risk_guess=RiskLevel.LOW,
            )

        action = ActionStep(
            action_type=ActionType.OPEN_APP,
            target="战网",
            risk_level=RiskLevel.LOW,
            reason="Open the requested local app.",
        )
        return PlannerResult(
            intent_summary="Open Battle.net",
            action_plan=ActionPlan(plan_name="open-app", source="test", steps=[action]),
            risk_guess=RiskLevel.LOW,
        )


class RefreshCountingInventoryStore:
    def __init__(self) -> None:
        self.refresh_calls = 0

    def ensure(self, *, refresh: bool = False):
        if refresh:
            self.refresh_calls += 1

        class Inventory:
            applications = [object()]

        return Inventory()


class MissingAppThenSuccessExecutor:
    def __init__(self) -> None:
        self.app_inventory_store = RefreshCountingInventoryStore()

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        if action.params.get("executable_path"):
            return ExecutionStepResult(
                step_index=step_index,
                action=action,
                status=ExecutionStatus.SUCCESS,
                message=f"[{trace_id}] opened {action.target}",
            )
        return ExecutionStepResult(
            step_index=step_index,
            action=action,
            status=ExecutionStatus.FAILED,
            message=f"[{trace_id}] app not found",
            diagnosis=ExecutionDiagnosis(
                code="APP_NOT_IN_INVENTORY",
                message="App was not found in inventory.",
                details={"target": action.target},
                remedy="Refresh app_inventory.json.",
            ),
        )


class ContextExplodingProvider:
    def get_context(self) -> ContextSnapshot:
        raise RuntimeError("context boom")


class PlannerExplodingProvider:
    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        raise RuntimeError("planner boom")


class ReviewerExplodingProvider:
    def review(
        self,
        request: WorkflowRequest,
        planner_result: PlannerResult,
        policy_decision,
        context: ContextSnapshot,
    ):
        raise RuntimeError("reviewer boom")


class WorkflowOrchestratorTests(unittest.TestCase):
    def test_dry_run_prepares_without_real_execution(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="开始做周报", run_mode=RunMode.DRY_RUN)
        )

        self.assertEqual(trace.status, WorkflowStatus.DRY_RUN_READY)
        self.assertEqual(trace.step_results, [])
        self.assertEqual(len(trace.planner_result.action_plan.steps), 3)

    def test_fake_planner_can_open_known_website(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="帮我打开知乎", run_mode=RunMode.DRY_RUN)
        )

        steps = trace.planner_result.action_plan.steps
        self.assertEqual(trace.planner_result.action_plan.plan_name, "open-website")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action_type.value, "open_url")
        self.assertEqual(steps[0].target, "https://www.zhihu.com")

    def test_fake_planner_can_open_explicit_domain(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="帮我打开 openai.com", run_mode=RunMode.DRY_RUN)
        )

        steps = trace.planner_result.action_plan.steps
        self.assertEqual(trace.planner_result.action_plan.plan_name, "open-website")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action_type.value, "open_url")
        self.assertEqual(steps[0].target, "https://openai.com")

    def test_fake_planner_searches_unknown_website_name(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="帮我打开豆瓣", run_mode=RunMode.DRY_RUN)
        )

        steps = trace.planner_result.action_plan.steps
        self.assertEqual(trace.planner_result.action_plan.plan_name, "open-website")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action_type.value, "open_url")
        self.assertTrue(steps[0].target.startswith("https://www.baidu.com/s?wd="))

    def test_fake_planner_searches_weather_lookup(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="查询今天西安天气", run_mode=RunMode.DRY_RUN)
        )

        steps = trace.planner_result.action_plan.steps
        self.assertEqual(trace.planner_result.action_plan.plan_name, "web-lookup")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action_type.value, "answer_query")
        self.assertEqual(steps[0].target, "查询今天西安天气")

    def test_fake_planner_can_open_local_app_wording(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="打开 Cursor 应用", run_mode=RunMode.DRY_RUN)
        )

        steps = trace.planner_result.action_plan.steps
        self.assertEqual(trace.planner_result.action_plan.plan_name, "open-app")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action_type.value, "open_app")
        self.assertEqual(steps[0].target, "Cursor")

    def test_fake_planner_refines_existing_draft_plan(self) -> None:
        current_plan = ActionPlan(
            plan_name="writing",
            source="test",
            steps=[
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Notion",
                    risk_level=RiskLevel.LOW,
                    reason="Open notes.",
                ),
                ActionStep(
                    action_type=ActionType.OPEN_URL,
                    target="https://example.com",
                    risk_level=RiskLevel.LOW,
                    reason="Open reference page.",
                ),
            ],
        )
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(
                user_request="Refine writing plan",
                run_mode=RunMode.DRY_RUN,
                plan_refinement=build_plan_refinement_context(
                    original_goal="Start writing",
                    current_plan=current_plan,
                    user_refinement="不要打开浏览器，改成 Obsidian",
                    revision_index=2,
                ),
            )
        )

        steps = trace.planner_result.action_plan.steps
        self.assertEqual(trace.planner_result.action_plan.source, "fake_planner_refinement")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action_type, ActionType.OPEN_APP)
        self.assertEqual(steps[0].target, "Obsidian")

    def test_fake_planner_rejects_unsafe_shell_request(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="帮我运行 PowerShell 脚本清理电脑", run_mode=RunMode.DRY_RUN)
        )

        self.assertEqual(trace.status, WorkflowStatus.REJECTED)
        self.assertTrue(trace.planner_result.requires_clarification)
        self.assertEqual(trace.planner_result.risk_guess, RiskLevel.HIGH)
        self.assertEqual(trace.planner_result.action_plan.steps, [])

    def test_fake_planner_can_focus_app(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="切到 Cursor", run_mode=RunMode.DRY_RUN)
        )

        steps = trace.planner_result.action_plan.steps
        self.assertEqual(trace.planner_result.action_plan.plan_name, "focus-app")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action_type.value, "focus_app")
        self.assertEqual(steps[0].target, "Cursor")

    def test_fake_planner_can_open_known_project_folder(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="打开下载文件夹", run_mode=RunMode.DRY_RUN)
        )

        steps = trace.planner_result.action_plan.steps
        self.assertEqual(trace.planner_result.action_plan.plan_name, "open-project")
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].action_type.value, "open_project")
        self.assertEqual(steps[0].target, "下载文件夹")

    def test_execute_all_runs_existing_dry_run_trace(self) -> None:
        orchestrator = build_orchestrator()
        dry_trace = orchestrator.run(
            WorkflowRequest(user_request="write setup", run_mode=RunMode.DRY_RUN)
        )

        executed_trace = orchestrator.execute_all(dry_trace.trace_id)

        self.assertEqual(executed_trace.status, WorkflowStatus.COMPLETED)
        self.assertEqual(len(executed_trace.step_results), 3)
        self.assertEqual(executed_trace.step_results[0].action.target, "Obsidian")

    def test_trace_keeps_orchestrator_backend_metadata(self) -> None:
        orchestrator = WorkflowOrchestrator(
            planner=FakePlanner(),
            reviewer=FakeReviewer(),
            executor=FakeExecutor(),
            context_provider=FakeContextProvider(),
            storage=InMemoryStorage(),
            policy_engine=PolicyEngine(),
            ai_backend="real",
            provider_config_path="runtime/data/model_provider.json",
        )

        trace = orchestrator.run(
            WorkflowRequest(user_request="write setup", run_mode=RunMode.DRY_RUN)
        )

        self.assertEqual(trace.ai_backend, "real")
        self.assertEqual(trace.provider_config_path, "runtime/data/model_provider.json")

    def test_prepare_failure_in_context_becomes_structured_failed_trace(self) -> None:
        storage = InMemoryStorage()
        orchestrator = WorkflowOrchestrator(
            planner=FakePlanner(),
            reviewer=FakeReviewer(),
            executor=FakeExecutor(),
            context_provider=ContextExplodingProvider(),
            storage=storage,
            policy_engine=PolicyEngine(),
        )

        trace = orchestrator.run(
            WorkflowRequest(user_request="write setup", run_mode=RunMode.DRY_RUN)
        )

        self.assertEqual(trace.status, WorkflowStatus.FAILED)
        self.assertIsNotNone(trace.prepare_error)
        self.assertEqual(trace.prepare_error.code, "PREPARE_CONTEXT_FAILED")
        self.assertEqual(trace.planner_result.action_plan.steps, [])
        self.assertFalse(trace.policy_decision.approved)
        self.assertFalse(trace.review_result.approved)
        self.assertEqual(storage.get_trace(trace.trace_id).prepare_error.code, "PREPARE_CONTEXT_FAILED")

    def test_prepare_failure_in_planner_becomes_structured_failed_trace(self) -> None:
        orchestrator = WorkflowOrchestrator(
            planner=PlannerExplodingProvider(),
            reviewer=FakeReviewer(),
            executor=FakeExecutor(),
            context_provider=FakeContextProvider(),
            storage=InMemoryStorage(),
            policy_engine=PolicyEngine(),
        )

        trace = orchestrator.run(
            WorkflowRequest(user_request="write setup", run_mode=RunMode.DRY_RUN)
        )

        self.assertEqual(trace.status, WorkflowStatus.FAILED)
        self.assertIsNotNone(trace.prepare_error)
        self.assertEqual(trace.prepare_error.code, "PREPARE_PLANNER_FAILED")
        self.assertEqual(trace.prepare_error.details["stage"], "planner")

    def test_prepare_failure_in_reviewer_becomes_structured_failed_trace(self) -> None:
        orchestrator = WorkflowOrchestrator(
            planner=FakePlanner(),
            reviewer=ReviewerExplodingProvider(),
            executor=FakeExecutor(),
            context_provider=FakeContextProvider(),
            storage=InMemoryStorage(),
            policy_engine=PolicyEngine(),
        )

        trace = orchestrator.run(
            WorkflowRequest(user_request="write setup", run_mode=RunMode.DRY_RUN)
        )

        self.assertEqual(trace.status, WorkflowStatus.FAILED)
        self.assertIsNotNone(trace.prepare_error)
        self.assertEqual(trace.prepare_error.code, "PREPARE_REVIEWER_FAILED")
        self.assertIn("reviewer boom", trace.prepare_error.message)

    def test_step_by_step_executes_only_one_step(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="开始写作", run_mode=RunMode.STEP_BY_STEP)
        )

        self.assertEqual(trace.status, WorkflowStatus.PARTIAL)
        self.assertEqual(len(trace.step_results), 1)
        self.assertEqual(trace.step_results[0].action.target, "Obsidian")

    def test_normal_mode_executes_all_steps(self) -> None:
        orchestrator = build_orchestrator()
        trace = orchestrator.run(
            WorkflowRequest(user_request="开始做周报", run_mode=RunMode.NORMAL)
        )

        self.assertEqual(trace.status, WorkflowStatus.COMPLETED)
        self.assertEqual(len(trace.step_results), 3)

    def test_repeated_failure_limit_stops_trace(self) -> None:
        storage = InMemoryStorage()
        orchestrator = WorkflowOrchestrator(
            planner=RepeatedFailurePlanner(),
            reviewer=FakeReviewer(),
            executor=AlwaysFailExecutor(),
            context_provider=FakeContextProvider(),
            storage=storage,
            policy_engine=PolicyEngine(),
            max_failed_attempts_per_action=1,
        )
        trace = orchestrator.run(WorkflowRequest(user_request="repeat", run_mode=RunMode.DRY_RUN))
        first = orchestrator.execute_step(trace.trace_id, 0)
        first.status = WorkflowStatus.PARTIAL
        storage.save_trace(first)

        stopped = orchestrator.execute_step(trace.trace_id, 1)

        self.assertEqual(stopped.status, WorkflowStatus.STOPPED)
        self.assertEqual(stopped.step_results[-1].status, ExecutionStatus.CANCELLED)
        self.assertIsNotNone(stopped.step_results[-1].diagnosis)
        self.assertEqual(stopped.step_results[-1].diagnosis.code, "RETRY_LIMIT_REACHED")

    def test_failed_step_can_replan_and_continue_with_recovery_step(self) -> None:
        storage = InMemoryStorage()
        planner = RecoveringPlanner()
        orchestrator = WorkflowOrchestrator(
            planner=planner,
            reviewer=FakeReviewer(),
            executor=FailMissingExecutor(),
            context_provider=FakeContextProvider(),
            storage=storage,
            policy_engine=PolicyEngine(),
        )

        trace = orchestrator.run(WorkflowRequest(user_request="open my folder", run_mode=RunMode.NORMAL))

        self.assertEqual(trace.status, WorkflowStatus.COMPLETED)
        self.assertEqual(trace.recovery_attempts, 1)
        self.assertEqual(len(trace.recovery_events), 1)
        self.assertEqual(trace.recovery_events[0].recovery_status, "planned")
        self.assertIsNotNone(planner.recovery_context_seen)
        self.assertEqual(planner.recovery_context_seen.failure_code, "TARGET_NOT_FOUND")
        self.assertEqual([result.status for result in trace.step_results], [ExecutionStatus.FAILED, ExecutionStatus.SUCCESS])
        self.assertEqual(trace.step_results[1].action.target, "D:/Recovered")
        self.assertEqual(
            [step.target for step in trace.planner_result.action_plan.steps],
            ["missing", "D:/Recovered"],
        )

    def test_local_app_execution_failure_can_replan_window_recovery(self) -> None:
        storage = InMemoryStorage()
        planner = LocalAppFailurePlanner()
        orchestrator = WorkflowOrchestrator(
            planner=planner,
            reviewer=FakeReviewer(),
            executor=LocalAppLaunchFailExecutor(),
            context_provider=FakeContextProvider(),
            storage=storage,
            policy_engine=PolicyEngine(),
        )

        trace = orchestrator.run(WorkflowRequest(user_request="open battle.net", run_mode=RunMode.NORMAL))

        self.assertEqual(trace.status, WorkflowStatus.COMPLETED)
        self.assertEqual(planner.calls, 2)
        self.assertEqual(trace.recovery_attempts, 1)
        self.assertEqual(len(trace.recovery_events), 1)
        self.assertEqual(trace.recovery_events[0].recovery_status, "planned")
        self.assertEqual(trace.recovery_events[0].failure_code, "APP_PROCESS_RUNNING_NO_WINDOW")
        self.assertIsNotNone(planner.recovery_context_seen)
        self.assertEqual(planner.recovery_context_seen.recovery_category, "window_state")
        self.assertEqual([result.status for result in trace.step_results], [ExecutionStatus.FAILED, ExecutionStatus.SUCCESS])
        self.assertEqual(trace.step_results[1].action.action_type, ActionType.FOCUS_WINDOW)

    def test_terminal_window_failure_stops_without_model_recovery(self) -> None:
        storage = InMemoryStorage()
        planner = TerminalRecoveryPlanner()
        orchestrator = WorkflowOrchestrator(
            planner=planner,
            reviewer=FakeReviewer(),
            executor=WindowEnumerationFailExecutor(),
            context_provider=FakeContextProvider(),
            storage=storage,
            policy_engine=PolicyEngine(),
        )

        trace = orchestrator.run(WorkflowRequest(user_request="list windows", run_mode=RunMode.NORMAL))

        self.assertEqual(trace.status, WorkflowStatus.STOPPED)
        self.assertEqual(planner.calls, 1)
        self.assertEqual(trace.recovery_attempts, 0)
        self.assertEqual(len(trace.recovery_events), 1)
        self.assertEqual(trace.recovery_events[0].recovery_status, "stopped")
        self.assertEqual(trace.recovery_events[0].failure_code, "WINDOW_ENUMERATION_FAILED")

    def test_recovery_plan_repeating_exact_failed_action_is_stopped(self) -> None:
        storage = InMemoryStorage()
        orchestrator = WorkflowOrchestrator(
            planner=RepeatingRecoveryPlanner(),
            reviewer=FakeReviewer(),
            executor=AlwaysFailExecutor(),
            context_provider=FakeContextProvider(),
            storage=storage,
            policy_engine=PolicyEngine(),
        )

        trace = orchestrator.run(WorkflowRequest(user_request="repeat missing folder", run_mode=RunMode.NORMAL))

        self.assertEqual(trace.status, WorkflowStatus.STOPPED)
        self.assertEqual(trace.recovery_attempts, 1)
        self.assertEqual(len(trace.step_results), 1)
        self.assertEqual(trace.recovery_events[0].recovery_status, "blocked")
        self.assertIn("repeated the exact same failed", trace.recovery_events[0].message)

    def test_app_inventory_failure_refreshes_inventory_before_model_recovery(self) -> None:
        storage = InMemoryStorage()
        planner = AppInventoryRecoveryPlanner()
        executor = MissingAppThenSuccessExecutor()
        orchestrator = WorkflowOrchestrator(
            planner=planner,
            reviewer=FakeReviewer(),
            executor=executor,
            context_provider=FakeContextProvider(),
            storage=storage,
            policy_engine=PolicyEngine(),
        )

        trace = orchestrator.run(WorkflowRequest(user_request="打开战网应用", run_mode=RunMode.NORMAL))

        self.assertEqual(trace.status, WorkflowStatus.COMPLETED)
        self.assertEqual(executor.app_inventory_store.refresh_calls, 1)
        self.assertIsNotNone(planner.recovery_context_seen)
        self.assertEqual(planner.recovery_context_seen.recovery_category, "local_app_inventory")
        self.assertEqual(planner.recovery_context_seen.recovery_strategy, "refresh_inventory_and_model_match")
        self.assertEqual([event.recovery_status for event in trace.recovery_events], ["diagnostic", "planned"])
        self.assertIn("Refreshed app inventory", trace.recovery_events[0].message)
        self.assertEqual(trace.step_results[1].action.params["executable_path"], "D:/Battle.net/Battle.net.exe")


if __name__ == "__main__":
    unittest.main()
