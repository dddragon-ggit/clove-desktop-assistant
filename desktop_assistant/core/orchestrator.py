from __future__ import annotations

import time
from datetime import datetime
from uuid import uuid4

from ..action_trust import action_trust_key
from ..models import (
    ActionPlan,
    ActionStep,
    ContextSnapshot,
    DebugRunRecord,
    ExecutionDiagnosis,
    ExecutionStatus,
    ExecutionStepResult,
    PlannerResult,
    PolicyDecision,
    PolicyIssue,
    ReviewResult,
    RiskLevel,
    RunMode,
    UserDecision,
    WorkflowStatus,
    WorkflowTrace,
)
from ..protocols import ContextProviderProtocol, ExecutorProtocol, PlannerProtocol, ReviewerProtocol, StorageProtocol
from .orchestrator_recovery import WorkflowRecoveryMixin
from .policy import PolicyEngine
from .recovery import RecoveryController


class WorkflowOrchestrator(WorkflowRecoveryMixin):
    """Coordinate planner, policy, reviewer, executor, and storage."""

    def __init__(
        self,
        planner: PlannerProtocol,
        reviewer: ReviewerProtocol,
        executor: ExecutorProtocol,
        context_provider: ContextProviderProtocol,
        storage: StorageProtocol,
        policy_engine: PolicyEngine,
        max_failed_attempts_per_action: int = 3,
        max_recovery_attempts_per_trace: int = 3,
        recovery_controller: RecoveryController | None = None,
        ai_backend: str = "fake",
        provider_config_path: str | None = None,
    ) -> None:
        self.planner = planner
        self.reviewer = reviewer
        self.executor = executor
        self.context_provider = context_provider
        self.storage = storage
        self.policy_engine = policy_engine
        self.max_failed_attempts_per_action = max(1, max_failed_attempts_per_action)
        self.max_recovery_attempts_per_trace = max(0, max_recovery_attempts_per_trace)
        self.recovery_controller = recovery_controller or RecoveryController()
        self.ai_backend = ai_backend
        self.provider_config_path = provider_config_path

    def run(self, request):
        trace = self.prepare(request)
        if trace.status in {WorkflowStatus.REJECTED, WorkflowStatus.CANCELLED, WorkflowStatus.FAILED, WorkflowStatus.STOPPED}:
            return trace

        if request.run_mode == RunMode.DRY_RUN:
            trace.status = WorkflowStatus.DRY_RUN_READY
            self.storage.save_trace(trace)
            self._save_debug_run(trace, current_step=0)
            return trace

        if request.run_mode == RunMode.STEP_BY_STEP:
            return self.execute_step(trace.trace_id, request.current_step)

        if request.run_mode == RunMode.MODULE_TEST:
            return trace

        return self.execute_all(trace.trace_id)

    def prepare(self, request):
        prepare_started = time.perf_counter()
        timings: dict[str, float] = {}
        trace_id = str(uuid4())
        context: ContextSnapshot | None = None
        context_started = time.perf_counter()
        try:
            context = self.context_provider.get_context()
        except Exception as exc:  # noqa: BLE001 - prepare failures should become structured traces
            timings["context_seconds"] = _elapsed(context_started)
            return self._prepare_failure_trace(
                trace_id=trace_id,
                request=request,
                stage="context",
                error=exc,
                context=context,
                timings=timings,
                prepare_started=prepare_started,
            )
        timings["context_seconds"] = _elapsed(context_started)
        planner_started = time.perf_counter()
        try:
            planner_result = self.planner.plan(request, context)
        except Exception as exc:  # noqa: BLE001 - prepare failures should become structured traces
            timings["planner_seconds"] = _elapsed(planner_started)
            return self._prepare_failure_trace(
                trace_id=trace_id,
                request=request,
                stage="planner",
                error=exc,
                context=context,
                timings=timings,
                prepare_started=prepare_started,
            )
        timings["planner_seconds"] = _elapsed(planner_started)
        policy_started = time.perf_counter()
        try:
            policy_decision = self.policy_engine.evaluate(
                planner_result.action_plan,
                planner_risk_guess=planner_result.risk_guess,
            )
        except Exception as exc:  # noqa: BLE001 - prepare failures should become structured traces
            timings["policy_seconds"] = _elapsed(policy_started)
            return self._prepare_failure_trace(
                trace_id=trace_id,
                request=request,
                stage="policy",
                error=exc,
                context=context,
                timings=timings,
                prepare_started=prepare_started,
            )
        timings["policy_seconds"] = _elapsed(policy_started)
        reviewer_started = time.perf_counter()
        try:
            review_result = self.reviewer.review(request, planner_result, policy_decision, context)
        except Exception as exc:  # noqa: BLE001 - prepare failures should become structured traces
            timings["reviewer_seconds"] = _elapsed(reviewer_started)
            return self._prepare_failure_trace(
                trace_id=trace_id,
                request=request,
                stage="reviewer",
                error=exc,
                context=context,
                timings=timings,
                prepare_started=prepare_started,
            )
        timings["reviewer_seconds"] = _elapsed(reviewer_started)
        timings["prepare_seconds"] = _elapsed(prepare_started)

        status = WorkflowStatus.PREPARED
        if request.user_decision == UserDecision.REJECT:
            status = WorkflowStatus.CANCELLED
        elif not policy_decision.approved or not review_result.approved:
            status = WorkflowStatus.REJECTED

        trace = WorkflowTrace(
            trace_id=trace_id,
            request=request,
            context=context,
            planner_result=planner_result,
            policy_decision=policy_decision,
            review_result=review_result,
            ai_backend=self.ai_backend,
            provider_config_path=self.provider_config_path,
            status=status,
            timings=timings,
        )
        self.storage.save_trace(trace)
        self._save_debug_run(trace, current_step=0)
        return trace

    def _prepare_failure_trace(
        self,
        *,
        trace_id: str,
        request,
        stage: str,
        error: Exception,
        context: ContextSnapshot | None,
        timings: dict[str, float],
        prepare_started: float,
    ) -> WorkflowTrace:
        timings["prepare_seconds"] = _elapsed(prepare_started)
        diagnosis = ExecutionDiagnosis(
            code=f"PREPARE_{stage.upper()}_FAILED",
            message=f"{_prepare_stage_label(stage)}失败：{type(error).__name__}: {error}",
            details={
                "stage": stage,
                "error_type": type(error).__name__,
                "error": str(error),
            },
            remedy=_prepare_stage_remedy(stage),
        )
        trace = WorkflowTrace(
            trace_id=trace_id,
            request=request,
            context=context or _fallback_context_snapshot(),
            planner_result=PlannerResult(
                intent_summary="准备阶段失败，未能生成可执行计划。",
                requires_clarification=False,
                action_plan=ActionPlan(
                    plan_name="prepare-failed",
                    source=f"prepare_error:{stage}",
                    steps=[],
                ),
                risk_guess=RiskLevel.MEDIUM,
                reasoning_summary=diagnosis.message,
            ),
            policy_decision=PolicyDecision(
                approved=False,
                risk_level=RiskLevel.MEDIUM,
                requires_user_confirmation=False,
                issues=[PolicyIssue(code=diagnosis.code, message=diagnosis.message)],
                action_decisions=[],
            ),
            review_result=ReviewResult(
                approved=False,
                risk_level=RiskLevel.MEDIUM,
                needs_user_confirmation=False,
                review_summary=diagnosis.message,
                issues=[diagnosis.message],
                rejection_reason=diagnosis.message,
            ),
            ai_backend=self.ai_backend,
            provider_config_path=self.provider_config_path,
            prepare_error=diagnosis,
            status=WorkflowStatus.FAILED,
            timings=timings,
        )
        self.storage.save_trace(trace)
        self._save_debug_run(trace, current_step=0)
        return trace

    def execute_all(self, trace_id: str) -> WorkflowTrace:
        trace = self.storage.get_trace(trace_id)

        while len(trace.step_results) < len(trace.planner_result.action_plan.steps):
            step_index = len(trace.step_results)
            trace = self.execute_step(trace_id, step_index)
            if trace.status in {
                WorkflowStatus.FAILED,
                WorkflowStatus.STOPPED,
                WorkflowStatus.REJECTED,
                WorkflowStatus.CANCELLED,
            }:
                return trace

        trace.status = WorkflowStatus.COMPLETED
        self.storage.save_trace(trace)
        self._save_debug_run(trace, current_step=len(trace.step_results))
        return trace

    def execute_step(self, trace_id: str, step_index: int) -> WorkflowTrace:
        trace = self.storage.get_trace(trace_id)
        if trace.status in {WorkflowStatus.REJECTED, WorkflowStatus.CANCELLED, WorkflowStatus.STOPPED}:
            return trace

        if step_index < len(trace.step_results):
            return trace

        steps = trace.planner_result.action_plan.steps
        if step_index >= len(steps):
            trace.status = WorkflowStatus.COMPLETED
            self.storage.save_trace(trace)
            return trace

        failed_attempts = self._failed_attempts_for_action(trace, steps[step_index])
        if failed_attempts >= self.max_failed_attempts_per_action:
            result = self._retry_limit_result(
                trace=trace,
                step_index=step_index,
                action=steps[step_index],
                failed_attempts=failed_attempts,
            )
            trace.step_results.append(result)
            trace.status = WorkflowStatus.STOPPED
            self.storage.save_trace(trace)
            self._save_debug_run(trace, current_step=step_index)
            return trace

        execute_started = time.perf_counter()
        result = self.executor.execute(steps[step_index], step_index, trace.trace_id)
        result.elapsed_seconds = _elapsed(execute_started)
        trace.step_results.append(result)
        trace.timings["execution_seconds"] = round(
            trace.timings.get("execution_seconds", 0.0) + (result.elapsed_seconds or 0.0),
            3,
        )

        if (
            result.status == ExecutionStatus.FAILED
            and self._failed_attempts_for_action(trace, steps[step_index]) >= self.max_failed_attempts_per_action
        ):
            trace.status = WorkflowStatus.STOPPED
        elif result.status == ExecutionStatus.FAILED:
            recovered_trace = self._attempt_recovery(trace, step_index, result)
            if recovered_trace is not None:
                return recovered_trace
            trace.status = WorkflowStatus.FAILED
        elif step_index == len(steps) - 1:
            trace.status = WorkflowStatus.COMPLETED
        else:
            trace.status = WorkflowStatus.PARTIAL

        self.storage.save_trace(trace)
        self._save_debug_run(trace, current_step=step_index + 1)
        return trace

    def _save_debug_run(self, trace: WorkflowTrace, current_step: int) -> None:
        debug_run = DebugRunRecord(
            id=str(uuid4()),
            trace_id=trace.trace_id,
            run_mode=trace.request.run_mode,
            trigger_source=trace.request.user_request,
            input_json=trace.request.model_dump(mode="json"),
            current_step=current_step,
            status=trace.status,
            snapshot_json=trace.model_dump(mode="json"),
        )
        self.storage.save_debug_run(debug_run)

    @staticmethod
    def _failed_attempts_for_action(trace: WorkflowTrace, action: ActionStep) -> int:
        target_key = action_trust_key(action)
        return sum(
            1
            for result in trace.step_results
            if result.status == ExecutionStatus.FAILED and action_trust_key(result.action) == target_key
        )

    @staticmethod
    def _retry_limit_result(
        *,
        trace: WorkflowTrace,
        step_index: int,
        action: ActionStep,
        failed_attempts: int,
    ) -> ExecutionStepResult:
        message = (
            f"[{trace.trace_id}] Stopped before retrying {action.action_type.value}:{action.target}; "
            f"the action already failed {failed_attempts} time(s)."
        )
        return ExecutionStepResult(
            step_index=step_index,
            action=action,
            status=ExecutionStatus.CANCELLED,
            message=message,
            diagnosis=ExecutionDiagnosis(
                code="RETRY_LIMIT_REACHED",
                message=message,
                details={
                    "failed_attempts": failed_attempts,
                    "action_type": action.action_type.value,
                    "target": action.target,
                },
                remedy="Stop automatic retries and ask the user to correct the target or change the plan.",
            ),
        )

def _elapsed(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 3)


def _fallback_context_snapshot() -> ContextSnapshot:
    now = datetime.now().astimezone()
    timezone_name = str(now.tzinfo) if now.tzinfo is not None else "unknown"
    return ContextSnapshot(
        local_time=now.isoformat(),
        date_label=now.strftime("%Y-%m-%d"),
        weekday=now.strftime("%A"),
        timezone=timezone_name,
        weather=None,
        holiday=False,
    )


def _prepare_stage_label(stage: str) -> str:
    return {
        "context": "上下文采样",
        "planner": "规划",
        "policy": "策略检查",
        "reviewer": "审查",
    }.get(stage, stage)


def _prepare_stage_remedy(stage: str) -> str:
    return {
        "context": "请检查本地环境、活动采样模块或上下文提供器。",
        "planner": "请检查规划器实现、模型配置或提示词输入。",
        "policy": "请检查策略引擎规则或规划结果格式。",
        "reviewer": "请检查审查器实现、模型响应或审查输入。",
    }.get(stage, "请检查准备阶段相关模块。")
