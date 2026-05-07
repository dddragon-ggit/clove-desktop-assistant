from __future__ import annotations

from dataclasses import dataclass

from ..action_trust import action_trust_key
from ..models import ActionStep, ActionType, ExecutionStatus, ExecutionStepResult, RiskLevel, WorkflowTrace


TERMINAL_FAILURE_CODES = {
    "APP_EXECUTABLE_NOT_ABSOLUTE",
    "APP_EXECUTABLE_NOT_EXE",
    "APP_LAUNCH_BLOCKED",
    "CAPABILITY_VALIDATION_FAILED",
    "HANDLER_NOT_REGISTERED",
    "QUERY_EMPTY",
    "WINDOW_ENUMERATION_FAILED",
    "WINDOW_LOOKUP_FAILED",
    "WINDOW_MANAGER_UNAVAILABLE",
}

LOCAL_APP_INVENTORY_FAILURE_CODES = {
    "APP_EXECUTABLE_MISSING",
    "APP_NOT_IN_INVENTORY",
}

WINDOW_RECOVERY_FAILURE_CODES = {
    "APP_FOCUS_REJECTED",
    "APP_LAUNCH_NOT_VERIFIED",
    "APP_PROCESS_RUNNING_NO_WINDOW",
    "APP_WINDOW_NOT_FOUND",
    "WINDOW_NOT_FOUND",
    "WINDOW_OPERATION_REJECTED",
}

WEB_QUERY_RECOVERY_FAILURE_CODES = {
    "WEB_QUERY_NO_DIRECT_ANSWER",
    "WEB_QUERY_TRANSPORT_ERROR",
}

UNSAFE_RECOVERY_ACTION_TYPES = {
    ActionType.CLOSE_WINDOW,
}


@dataclass(frozen=True)
class RecoveryDecision:
    should_recover: bool
    category: str
    strategy: str
    message: str
    guidance: tuple[str, ...] = ()
    refresh_app_inventory: bool = False
    stop_trace: bool = False
    recovery_status: str = "skipped"


class RecoveryController:
    """Decide whether a failed execution can be repaired automatically."""

    def __init__(self, *, max_failures_per_action_code: int = 2) -> None:
        self.max_failures_per_action_code = max(1, max_failures_per_action_code)

    def decide(
        self,
        *,
        trace: WorkflowTrace,
        step_index: int,
        failed_result: ExecutionStepResult,
        max_recovery_attempts_per_trace: int,
    ) -> RecoveryDecision:
        action = failed_result.action
        code = failed_result.diagnosis.code if failed_result.diagnosis is not None else "EXECUTION_FAILED"

        if failed_result.status != ExecutionStatus.FAILED:
            return RecoveryDecision(
                should_recover=False,
                category="not_failed",
                strategy="none",
                message="Recovery only applies to failed execution results.",
            )

        if action.action_type in UNSAFE_RECOVERY_ACTION_TYPES or action.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            return RecoveryDecision(
                should_recover=False,
                category="unsafe_to_retry",
                strategy="ask_user",
                message=(
                    f"Automatic recovery is disabled for {action.action_type.value} "
                    f"because the failed action risk is {action.risk_level.value}."
                ),
                guidance=("Ask the user before trying a different high-risk or destructive operation.",),
                stop_trace=True,
                recovery_status="stopped",
            )

        if trace.recovery_attempts >= max_recovery_attempts_per_trace:
            return RecoveryDecision(
                should_recover=False,
                category="recovery_limit_reached",
                strategy="stop",
                message=(
                    "Recovery was stopped because the trace already reached "
                    f"{max_recovery_attempts_per_trace} recovery attempt(s)."
                ),
                guidance=("Stop automatic retries and wait for user correction.",),
                stop_trace=True,
                recovery_status="stopped",
            )

        same_failure_count = self._failures_for_same_action_and_code(trace, action, code)
        if same_failure_count >= self.max_failures_per_action_code:
            return RecoveryDecision(
                should_recover=False,
                category="same_failure_repeated",
                strategy="stop",
                message=(
                    f"Recovery was stopped because {action.action_type.value}:{action.target} "
                    f"already failed with {code} {same_failure_count} time(s)."
                ),
                guidance=("Do not keep retrying the same action/failure pair.",),
                stop_trace=True,
                recovery_status="stopped",
            )

        if code in TERMINAL_FAILURE_CODES:
            return RecoveryDecision(
                should_recover=False,
                category="terminal_failure",
                strategy="ask_user",
                message=(
                    f"Automatic recovery was skipped for terminal failure {code}; "
                    "the user or runtime environment must be corrected first."
                ),
                guidance=("Show the failure code, details, and remedy to the user.",),
                stop_trace=True,
                recovery_status="stopped",
            )

        if code in LOCAL_APP_INVENTORY_FAILURE_CODES:
            return RecoveryDecision(
                should_recover=True,
                category="local_app_inventory",
                strategy="refresh_inventory_and_model_match",
                message=(
                    f"Recovering from {code}: refresh app inventory, then ask the planner "
                    "to rematch the user's requested local application."
                ),
                guidance=(
                    "Refresh app_inventory.json and app_name_index.json before replanning.",
                    "Use the app name index to choose the most likely installed local application.",
                    "If no confident installed-app match exists, ask the user to clarify instead of opening a web search.",
                    "Do not repeat the exact same open_app/focus_app action unless the target or params are corrected.",
                ),
                refresh_app_inventory=True,
                recovery_status="planned",
            )

        if code in WINDOW_RECOVERY_FAILURE_CODES:
            return RecoveryDecision(
                should_recover=True,
                category="window_state",
                strategy="inspect_windows_and_replan",
                message=(
                    f"Recovering from {code}: inspect visible windows and plan a safer "
                    "focus/restore/open action."
                ),
                guidance=(
                    "Prefer list_windows when the current visible window state is unknown.",
                    "Use focus_window, restore_window, or open_app only when the target is specific.",
                    "If no visible window can be matched, explain the failure and ask the user for the exact app/window.",
                    "Do not loop on the same failed window target.",
                ),
                recovery_status="planned",
            )

        if code in WEB_QUERY_RECOVERY_FAILURE_CODES:
            return RecoveryDecision(
                should_recover=True,
                category="information_query",
                strategy="alternate_source_or_search_fallback",
                message=(
                    f"Recovering from {code}: try a safer information-query fallback "
                    "or open a search page if direct answering is unavailable."
                ),
                guidance=(
                    "Try an alternate structured/source-backed query if available.",
                    "If direct answering cannot be done, fall back to opening a search URL for the original query.",
                    "Be explicit about source or transport failure in the final result.",
                ),
                recovery_status="planned",
            )

        return RecoveryDecision(
            should_recover=True,
            category="generic",
            strategy="minimal_corrective_replan",
            message=f"Recovering from {code}: ask the planner for a minimal corrected action.",
            guidance=(
                "Generate only the smallest corrective step or ask for clarification.",
                "Avoid repeating the exact same failed action/target/params.",
            ),
            recovery_status="planned",
        )

    def _failures_for_same_action_and_code(
        self,
        trace: WorkflowTrace,
        action: ActionStep,
        failure_code: str,
    ) -> int:
        key = action_trust_key(action)
        count = 0
        for result in trace.step_results:
            if result.status != ExecutionStatus.FAILED:
                continue
            if action_trust_key(result.action) != key:
                continue
            result_code = result.diagnosis.code if result.diagnosis is not None else "EXECUTION_FAILED"
            if result_code == failure_code:
                count += 1
        return count

