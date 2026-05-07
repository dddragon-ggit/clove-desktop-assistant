from __future__ import annotations

import traceback
from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from ..adapters.windows_executor import WindowsExecutor
from ..confirmation import ConfirmationChoice, ConfirmationService
from ..demo import build_orchestrator
from ..models import ActionPlan, ActionStep, ActionType, ExecutionStatus, ExecutionStepResult, RiskLevel, WorkflowRequest
from ..storage.sqlite import SQLiteStorage
from .execution_feedback import workspace_execution_feedback
from .localization import action_label
from .view_model import summarize_trace


@dataclass(frozen=True)
class WorkerFailure:
    stage: str
    error_type: str
    message: str
    details: str = ""
    user_message: str = ""


@dataclass(frozen=True)
class WorkspaceExecutionSummary:
    todo_id: str | None
    trace_id: str
    choice: ConfirmationChoice
    accepted: bool
    status: str
    message: str
    results: list[ExecutionStepResult]
    trusted_keys: list[str]
    executed_actions: list[dict[str, str]]


class DryRunWorker(QObject):
    finished = Signal(object)
    failed = Signal(object)
    progress = Signal(str)

    def __init__(self, workflow_request: WorkflowRequest, ai_backend: str) -> None:
        super().__init__()
        self.workflow_request = workflow_request
        self.ai_backend = ai_backend

    def run(self) -> None:
        try:
            if self.ai_backend == "real":
                self.progress.emit(
                    "真实后端正在运行：意图理解 -> 任务规划 -> 安全审查。"
                    "可能需要 30-90 秒。"
                )
            else:
                self.progress.emit("模拟后端正在生成本地预演计划。")
            orchestrator, _provider_info = build_orchestrator(
                storage_backend="sqlite",
                ai_backend=self.ai_backend,
            )
            self.progress.emit("规划器、策略检查和审查器正在处理请求。")
            trace = orchestrator.run(self.workflow_request)
            self.finished.emit(summarize_trace(trace))
        except Exception as exc:  # noqa: BLE001 - UI workers must never fail silently
            self.failed.emit(
                _worker_failure(
                    stage="dry_run",
                    exc=exc,
                    user_message="预演规划过程中出现异常。",
                )
            )


class ExecuteTraceWorker(QObject):
    finished = Signal(object)
    failed = Signal(object)
    progress = Signal(str)

    def __init__(self, trace_id: str) -> None:
        super().__init__()
        self.trace_id = trace_id

    def run(self) -> None:
        try:
            self.progress.emit("正在执行已确认的安全动作。")
            trace = SQLiteStorage().get_trace(self.trace_id)
            orchestrator, _provider_info = build_orchestrator(
                storage_backend="sqlite",
                ai_backend=trace.ai_backend,
                provider_config_path=trace.provider_config_path,
            )
            orchestrator.executor = WindowsExecutor()
            executed_trace = orchestrator.execute_all(self.trace_id)
            self.finished.emit(summarize_trace(executed_trace))
        except Exception as exc:  # noqa: BLE001 - UI workers must never fail silently
            self.failed.emit(
                _worker_failure(
                    stage="execute_trace",
                    exc=exc,
                    user_message="执行已确认动作时出现异常。",
                )
            )


class WorkspaceExecuteWorker(QObject):
    finished = Signal(object)
    failed = Signal(object)
    progress = Signal(str)

    def __init__(
        self,
        plan: ActionPlan,
        *,
        todo_id: str | None,
        choice: ConfirmationChoice,
        confirmation_service: ConfirmationService | None = None,
        executor: WindowsExecutor | None = None,
    ) -> None:
        super().__init__()
        self.plan = plan
        self.todo_id = todo_id
        self.choice = choice
        self.confirmation_service = confirmation_service or ConfirmationService()
        self.executor = executor or WindowsExecutor()

    def run(self) -> None:
        try:
            flow = self.confirmation_service.build_flow(self.plan)
            if self.choice not in flow.choices:
                self.finished.emit(
                    WorkspaceExecutionSummary(
                        todo_id=self.todo_id,
                        trace_id="",
                        choice=self.choice,
                        accepted=False,
                        status="rejected",
                        message="当前策略不允许这个确认选择。",
                        results=[],
                        trusted_keys=[],
                        executed_actions=[],
                    )
                )
                return
            apply_result = self.confirmation_service.apply_choice(self.plan, self.choice)
            if not apply_result.accepted:
                self.finished.emit(
                    WorkspaceExecutionSummary(
                        todo_id=self.todo_id,
                        trace_id="",
                        choice=self.choice,
                        accepted=False,
                        status="rejected",
                        message=apply_result.message,
                        results=[],
                        trusted_keys=apply_result.trusted_keys,
                        executed_actions=[],
                    )
                )
                return
            trace_id = f"workspace-{uuid4()}"
            self.progress.emit("正在执行已确认的工作区动作。")
            results = [
                self.executor.execute(step, index, trace_id)
                for index, step in enumerate(self.plan.steps)
            ]
            status = _workspace_status(results)
            message = workspace_execution_feedback(results, status=status)
            self.finished.emit(
                WorkspaceExecutionSummary(
                    todo_id=self.todo_id,
                    trace_id=trace_id,
                    choice=self.choice,
                    accepted=True,
                    status=status,
                    message=message,
                    results=results,
                    trusted_keys=apply_result.trusted_keys,
                    executed_actions=_executed_actions(results),
                )
            )
        except Exception as exc:  # noqa: BLE001 - UI workers must never fail silently
            self.failed.emit(
                _worker_failure(
                    stage="workspace_execute",
                    exc=exc,
                    user_message="执行工作区动作时出现异常。",
                )
            )


def _workspace_status(results: list[ExecutionStepResult]) -> str:
    if not results:
        return "skipped"
    if all(result.status == ExecutionStatus.SUCCESS for result in results):
        return "success"
    if all(result.status == ExecutionStatus.SKIPPED for result in results):
        return "skipped"
    if any(result.status == ExecutionStatus.FAILED for result in results) and any(
        result.status == ExecutionStatus.SUCCESS for result in results
    ):
        return "partial"
    if any(result.status == ExecutionStatus.FAILED for result in results):
        return "failed"
    return "partial"


def _executed_actions(results: list[ExecutionStepResult]) -> list[dict[str, str]]:
    return [
        {
            "action_type": result.action.action_type.value,
            "target": result.action.target,
            "risk_level": result.action.risk_level.value,
            "reason": result.action.reason,
            "status": result.status.value,
            "message": result.message,
        }
        for result in results
    ]


class WindowListWorker(QObject):
    finished = Signal(object)
    failed = Signal(object)
    progress = Signal(str)

    def __init__(self, limit: int = 50) -> None:
        super().__init__()
        self.limit = limit

    def run(self) -> None:
        try:
            self.progress.emit("正在刷新可见窗口。")
            result = WindowsExecutor().execute(
                ActionStep(
                    action_type=ActionType.LIST_WINDOWS,
                    target="visible",
                    params={"limit": self.limit},
                    risk_level=RiskLevel.LOW,
                    reason="Manual refresh from the window debug panel.",
                ),
                step_index=0,
                trace_id="ui-window",
            )
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - UI workers must never fail silently
            self.failed.emit(
                _worker_failure(
                    stage="window_list",
                    exc=exc,
                    user_message="刷新窗口列表时出现异常。",
                )
            )


class WindowActionWorker(QObject):
    finished = Signal(object)
    failed = Signal(object)
    progress = Signal(str)

    def __init__(self, action_type: ActionType, target: str, params: dict, risk_level: RiskLevel) -> None:
        super().__init__()
        self.action_type = action_type
        self.target = target
        self.params = params
        self.risk_level = risk_level

    def run(self) -> None:
        try:
            self.progress.emit(f"正在执行{action_label(self.action_type.value)}：{self.target}")
            result = WindowsExecutor().execute(
                ActionStep(
                    action_type=self.action_type,
                    target=self.target,
                    params=self.params,
                    risk_level=self.risk_level,
                    reason="Manual action from the window debug panel.",
                ),
                step_index=0,
                trace_id="ui-window",
            )
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - UI workers must never fail silently
            self.failed.emit(
                _worker_failure(
                    stage="window_action",
                    exc=exc,
                    user_message="执行窗口动作时出现异常。",
                )
            )


def worker_failure_text(error: object) -> str:
    if isinstance(error, WorkerFailure):
        lines = [
            error.user_message or "执行过程中出现异常。",
            f"{error.error_type}: {error.message}",
            "可以稍后重试；如果反复出现，需要查看完整错误堆栈。",
        ]
        return "\n".join(lines)
    return str(error)


def worker_failure_debug_text(error: object) -> str:
    if isinstance(error, WorkerFailure):
        lines = [worker_failure_text(error)]
        if error.details:
            lines.extend(["", error.details])
        return "\n".join(lines)
    return str(error)


def _worker_failure(*, stage: str, exc: Exception, user_message: str) -> WorkerFailure:
    return WorkerFailure(
        stage=stage,
        error_type=type(exc).__name__,
        message=str(exc),
        details=traceback.format_exc(limit=8),
        user_message=user_message,
    )
