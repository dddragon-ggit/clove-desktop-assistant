from __future__ import annotations

from ..models import ActionStep, ExecutionStatus, ExecutionStepResult


class FakeExecutor:
    """Fake executor that never touches the real system."""

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        if "missing" in action.target.lower():
            return ExecutionStepResult(
                step_index=step_index,
                action=action,
                status=ExecutionStatus.FAILED,
                message=f"[{trace_id}] Simulated failure: target not found.",
            )

        return ExecutionStepResult(
            step_index=step_index,
            action=action,
            status=ExecutionStatus.SUCCESS,
            message=f"[{trace_id}] Simulated execution for {action.action_type.value}:{action.target}",
        )
