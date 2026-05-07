from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ..models import ActionStep, ActionType, ExecutionDiagnosis, ExecutionStatus, ExecutionStepResult
from .registry import CapabilityRegistry


class CapabilityHandlerProtocol(Protocol):
    """Executable implementation for one registered capability."""

    action_type: ActionType

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        """Execute one validated action."""


class CapabilityExecutor:
    """Dispatch actions to capability handlers after shared registry validation."""

    def __init__(
        self,
        handlers: Iterable[CapabilityHandlerProtocol],
        *,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry.default()
        self.handlers = {handler.action_type: handler for handler in handlers}

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        try:
            issues = self.capability_registry.validate_action(action)
            if issues:
                return execution_failed(
                    action,
                    step_index,
                    f"[{trace_id}] Capability validation failed: "
                    + "; ".join(f"{issue.code}: {issue.message}" for issue in issues),
                    code="CAPABILITY_VALIDATION_FAILED",
                    details={"issues": [issue.model_dump(mode="json") for issue in issues]},
                    remedy="Review the action target and capability safety rules.",
                )

            handler = self.handlers.get(action.action_type)
            if handler is None:
                return execution_skipped(
                    action,
                    step_index,
                    f"[{trace_id}] No handler is registered for {action.action_type.value}.",
                    code="HANDLER_NOT_REGISTERED",
                    details={"action_type": action.action_type.value},
                    remedy="Enable a matching handler in the capability catalog.",
                )

            return handler.execute(action, step_index, trace_id)
        except OSError as exc:
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] OS error: {exc}",
                code="OS_ERROR",
                details={"error": str(exc)},
                remedy="Check whether the target exists and the OS allows this operation.",
            )
        except ValueError as exc:
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Invalid target: {exc}",
                code="INVALID_TARGET",
                details={"error": str(exc)},
                remedy="Correct the action target and try again.",
            )
        except Exception as exc:  # noqa: BLE001 - executor failures should be visible in traces
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Execution error: {type(exc).__name__}: {exc}",
                code="UNEXPECTED_EXECUTION_ERROR",
                details={"error_type": type(exc).__name__, "error": str(exc)},
                remedy="Inspect the debug snapshot and handler implementation.",
            )


class SimulatedCapabilityHandler:
    """Handler for capabilities that are modeled but not wired to real integrations yet."""

    handler_name = "simulated"

    def __init__(self, action_type: ActionType) -> None:
        self.action_type = action_type

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        return execution_success(
            action,
            step_index,
            f"[{trace_id}] Simulated {action.action_type.value}: {action.target}",
        )


def execution_success(
    action: ActionStep,
    step_index: int,
    message: str,
    *,
    metadata: dict | None = None,
) -> ExecutionStepResult:
    return ExecutionStepResult(
        step_index=step_index,
        action=action,
        status=ExecutionStatus.SUCCESS,
        message=message,
        metadata=metadata or {},
    )


def execution_failed(
    action: ActionStep,
    step_index: int,
    message: str,
    *,
    code: str = "EXECUTION_FAILED",
    details: dict | None = None,
    remedy: str | None = None,
    metadata: dict | None = None,
) -> ExecutionStepResult:
    return ExecutionStepResult(
        step_index=step_index,
        action=action,
        status=ExecutionStatus.FAILED,
        message=message,
        metadata=metadata or {},
        diagnosis=ExecutionDiagnosis(
            code=code,
            message=message,
            details=details or {},
            remedy=remedy,
        ),
    )


def execution_skipped(
    action: ActionStep,
    step_index: int,
    message: str,
    *,
    code: str = "EXECUTION_SKIPPED",
    details: dict | None = None,
    remedy: str | None = None,
    metadata: dict | None = None,
) -> ExecutionStepResult:
    return ExecutionStepResult(
        step_index=step_index,
        action=action,
        status=ExecutionStatus.SKIPPED,
        message=message,
        metadata=metadata or {},
        diagnosis=ExecutionDiagnosis(
            code=code,
            message=message,
            details=details or {},
            remedy=remedy,
        ),
    )
