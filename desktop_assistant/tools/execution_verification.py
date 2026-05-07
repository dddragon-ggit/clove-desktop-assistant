from __future__ import annotations

from typing import Any

from ..models import ActionType, ExecutionStatus, WorkflowTrace


def execution_ok(trace: WorkflowTrace) -> bool:
    if trace.status.value != "completed":
        return False
    return bool(trace.step_results) and all(
        step_result.status == ExecutionStatus.SUCCESS for step_result in trace.step_results
    )


def verification_ok(trace: WorkflowTrace, required_action_types: tuple[str, ...]) -> bool | None:
    if not required_action_types:
        return None
    required = set(required_action_types)
    verdicts = [
        step_verification_ok(step_result)
        for step_result in trace.step_results
        if step_result.action.action_type.value in required
    ]
    if not verdicts:
        return False
    return all(verdicts)


def step_verification_ok(step_result) -> bool:
    if step_result.status != ExecutionStatus.SUCCESS:
        return False
    action_type = step_result.action.action_type
    message = step_result.message.lower()
    if action_type == ActionType.OPEN_APP:
        return (
            "launched and verified" in message
            or "already running" in message
            or "focused" in message
        ) and "window verification is unavailable" not in message
    if action_type == ActionType.FOCUS_APP:
        return "focused app" in message
    return True


def execution_trace_payload(trace: WorkflowTrace) -> dict[str, Any]:
    return {
        "trace_id": trace.trace_id,
        "status": trace.status.value,
        "recovery_attempts": trace.recovery_attempts,
        "timings": trace.timings,
        "step_results": [
            {
                "step_index": result.step_index,
                "action_type": result.action.action_type.value,
                "target": result.action.target,
                "status": result.status.value,
                "message": result.message,
                "elapsed_seconds": result.elapsed_seconds,
                "metadata": result.metadata,
                "diagnosis": result.diagnosis.model_dump(mode="json") if result.diagnosis else None,
            }
            for result in trace.step_results
        ],
    }


_execution_ok = execution_ok
_verification_ok = verification_ok
_step_verification_ok = step_verification_ok
_execution_trace_payload = execution_trace_payload
