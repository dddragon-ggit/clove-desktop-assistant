from __future__ import annotations

from ..action_trust import action_trust_key
from ..models import (
    ActionStep,
    ExecutionStepResult,
    RecoveryContext,
    RecoveryEvent,
    WorkflowStatus,
    WorkflowTrace,
)
from .recovery import RecoveryDecision


class WorkflowRecoveryMixin:
    def _attempt_recovery(
        self,
        trace: WorkflowTrace,
        step_index: int,
        failed_result: ExecutionStepResult,
    ) -> WorkflowTrace | None:
        if self.max_recovery_attempts_per_trace == 0:
            return None

        failed_action = failed_result.action
        recovery_decision = self.recovery_controller.decide(
            trace=trace,
            step_index=step_index,
            failed_result=failed_result,
            max_recovery_attempts_per_trace=self.max_recovery_attempts_per_trace,
        )
        if not recovery_decision.should_recover:
            trace.recovery_events.append(
                RecoveryEvent(
                    failed_step_index=step_index,
                    failed_action_type=failed_action.action_type.value,
                    failed_target=failed_action.target,
                    failure_code=failed_result.diagnosis.code if failed_result.diagnosis else None,
                    recovery_status=recovery_decision.recovery_status,
                    message=recovery_decision.message,
                )
            )
            if recovery_decision.stop_trace:
                trace.status = WorkflowStatus.STOPPED
                self.storage.save_trace(trace)
                self._save_debug_run(trace, current_step=step_index + 1)
                return trace
            return None

        if recovery_decision.refresh_app_inventory:
            self._refresh_app_inventory_for_recovery(trace, step_index, failed_result, recovery_decision)

        recovery_context = self._build_recovery_context(
            trace=trace,
            step_index=step_index,
            failed_result=failed_result,
            recovery_decision=recovery_decision,
        )
        recovery_request = trace.request.model_copy(
            update={
                "user_request": self._recovery_user_request(trace.request.user_request, recovery_context),
                "recovery_context": recovery_context,
            }
        )

        try:
            recovery_planner_result = self.planner.plan(recovery_request, trace.context)
            recovery_policy = self.policy_engine.evaluate(
                recovery_planner_result.action_plan,
                planner_risk_guess=recovery_planner_result.risk_guess,
            )
            recovery_review = self.reviewer.review(
                recovery_request,
                recovery_planner_result,
                recovery_policy,
                trace.context,
            )
        except Exception as exc:  # noqa: BLE001 - recovery must fail closed and explain why
            trace.recovery_attempts += 1
            trace.recovery_events.append(
                RecoveryEvent(
                    failed_step_index=step_index,
                    failed_action_type=failed_action.action_type.value,
                    failed_target=failed_action.target,
                    failure_code=failed_result.diagnosis.code if failed_result.diagnosis else None,
                    recovery_status="failed",
                    message=f"Recovery planning failed: {type(exc).__name__}: {exc}",
                )
            )
            trace.status = WorkflowStatus.FAILED
            self.storage.save_trace(trace)
            self._save_debug_run(trace, current_step=step_index + 1)
            return trace

        trace.recovery_attempts += 1

        recovery_steps = [step.model_copy(deep=True) for step in recovery_planner_result.action_plan.steps]
        if self._recovery_repeats_failed_action(failed_action, recovery_steps):
            trace.recovery_events.append(
                RecoveryEvent(
                    failed_step_index=step_index,
                    failed_action_type=failed_action.action_type.value,
                    failed_target=failed_action.target,
                    failure_code=failed_result.diagnosis.code if failed_result.diagnosis else None,
                    recovery_status="blocked",
                    message=(
                        "Recovery plan was blocked because it repeated the exact same failed "
                        f"{failed_action.action_type.value}:{failed_action.target} action."
                    ),
                )
            )
            trace.status = WorkflowStatus.STOPPED
            self.storage.save_trace(trace)
            self._save_debug_run(trace, current_step=step_index + 1)
            return trace

        if (
            not recovery_policy.approved
            or not recovery_review.approved
            or recovery_planner_result.requires_clarification
            or not recovery_planner_result.action_plan.steps
        ):
            trace.recovery_events.append(
                RecoveryEvent(
                    failed_step_index=step_index,
                    failed_action_type=failed_action.action_type.value,
                    failed_target=failed_action.target,
                    failure_code=failed_result.diagnosis.code if failed_result.diagnosis else None,
                    recovery_status="blocked",
                    message=self._blocked_recovery_message(
                        recovery_planner_result,
                        recovery_policy,
                        recovery_review,
                    ),
                )
            )
            trace.status = WorkflowStatus.FAILED
            trace.review_result = recovery_review
            self.storage.save_trace(trace)
            self._save_debug_run(trace, current_step=step_index + 1)
            return trace

        insert_at = step_index + 1
        current_steps = trace.planner_result.action_plan.steps
        trace.planner_result.action_plan.steps = (
            current_steps[:insert_at] + recovery_steps + current_steps[insert_at:]
        )
        trace.planner_result.action_plan.plan_name = (
            f"{trace.planner_result.action_plan.plan_name}+recovery"
        )
        trace.planner_result.action_plan.source = (
            f"{trace.planner_result.action_plan.source}; recovery:{recovery_planner_result.action_plan.source}"
        )
        trace.planner_result.intent_summary = (
            f"{trace.planner_result.intent_summary} Recovery: {recovery_planner_result.intent_summary}"
        )
        trace.planner_result.reasoning_summary = "\n".join(
            part
            for part in [
                trace.planner_result.reasoning_summary,
                f"Recovery: {recovery_planner_result.reasoning_summary}",
            ]
            if part
        )
        trace.policy_decision = self.policy_engine.evaluate(
            trace.planner_result.action_plan,
            planner_risk_guess=recovery_planner_result.risk_guess,
        )
        trace.review_result = recovery_review
        trace.recovery_events.append(
            RecoveryEvent(
                failed_step_index=step_index,
                failed_action_type=failed_action.action_type.value,
                failed_target=failed_action.target,
                failure_code=failed_result.diagnosis.code if failed_result.diagnosis else None,
                recovery_status="planned",
                message=(
                    f"{recovery_decision.message} Inserted {len(recovery_steps)} recovery step(s) "
                    f"after failed step {step_index + 1}."
                ),
                inserted_steps=len(recovery_steps),
            )
        )
        trace.status = WorkflowStatus.PARTIAL
        self.storage.save_trace(trace)
        self._save_debug_run(trace, current_step=step_index + 1)
        return trace

    def _refresh_app_inventory_for_recovery(
        self,
        trace: WorkflowTrace,
        step_index: int,
        failed_result: ExecutionStepResult,
        recovery_decision: RecoveryDecision,
    ) -> None:
        store = getattr(self.executor, "app_inventory_store", None)
        ensure = getattr(store, "ensure", None)
        if not callable(ensure):
            trace.recovery_events.append(
                RecoveryEvent(
                    failed_step_index=step_index,
                    failed_action_type=failed_result.action.action_type.value,
                    failed_target=failed_result.action.target,
                    failure_code=failed_result.diagnosis.code if failed_result.diagnosis else None,
                    recovery_status="diagnostic",
                    message=(
                        f"{recovery_decision.message} App inventory refresh was skipped because "
                        "the current executor does not expose an app inventory store."
                    ),
                )
            )
            return
        try:
            inventory = ensure(refresh=True)
        except Exception as exc:  # noqa: BLE001 - recovery must continue to model clarification when refresh fails
            trace.recovery_events.append(
                RecoveryEvent(
                    failed_step_index=step_index,
                    failed_action_type=failed_result.action.action_type.value,
                    failed_target=failed_result.action.target,
                    failure_code=failed_result.diagnosis.code if failed_result.diagnosis else None,
                    recovery_status="diagnostic",
                    message=f"App inventory refresh failed during recovery: {type(exc).__name__}: {exc}",
                )
            )
            return
        count = len(getattr(inventory, "applications", []) or [])
        trace.recovery_events.append(
            RecoveryEvent(
                failed_step_index=step_index,
                failed_action_type=failed_result.action.action_type.value,
                failed_target=failed_result.action.target,
                failure_code=failed_result.diagnosis.code if failed_result.diagnosis else None,
                recovery_status="diagnostic",
                message=f"Refreshed app inventory during recovery; cached {count} app(s).",
            )
        )

    def _build_recovery_context(
        self,
        *,
        trace: WorkflowTrace,
        step_index: int,
        failed_result: ExecutionStepResult,
        recovery_decision: RecoveryDecision,
    ) -> RecoveryContext:
        diagnosis = failed_result.diagnosis
        failed_action = failed_result.action
        return RecoveryContext(
            original_user_request=trace.request.user_request,
            failed_step_index=step_index,
            failed_action_type=failed_action.action_type.value,
            failed_target=failed_action.target,
            failure_status=failed_result.status.value,
            failure_message=failed_result.message,
            failure_code=diagnosis.code if diagnosis else None,
            failure_details=diagnosis.details if diagnosis else {},
            suggested_remedy=diagnosis.remedy if diagnosis else None,
            previous_plan_name=trace.planner_result.action_plan.plan_name,
            failed_attempts_for_action=self._failed_attempts_for_action(trace, failed_action),
            recovery_attempt=trace.recovery_attempts + 1,
            recovery_category=recovery_decision.category,
            recovery_strategy=recovery_decision.strategy,
            recovery_guidance=list(recovery_decision.guidance),
        )

    @staticmethod
    def _recovery_user_request(user_request: str, recovery_context: RecoveryContext) -> str:
        return (
            f"{user_request}\n\n"
            "Previous execution failed. Generate a revised minimal plan that avoids repeating "
            "the same failed action unless the target or method is corrected.\n"
            f"Failed action: {recovery_context.failed_action_type} -> {recovery_context.failed_target}\n"
            f"Failure code: {recovery_context.failure_code or '-'}\n"
            f"Failure message: {recovery_context.failure_message}\n"
            f"Suggested remedy: {recovery_context.suggested_remedy or '-'}\n"
            f"Recovery strategy: {recovery_context.recovery_strategy or '-'}\n"
            "Recovery guidance:\n"
            + "\n".join(f"- {item}" for item in recovery_context.recovery_guidance)
        )

    @staticmethod
    def _recovery_repeats_failed_action(
        failed_action: ActionStep,
        recovery_steps: list[ActionStep],
    ) -> bool:
        failed_key = action_trust_key(failed_action)
        return any(action_trust_key(step) == failed_key for step in recovery_steps)

    @staticmethod
    def _blocked_recovery_message(
        recovery_planner_result,
        recovery_policy,
        recovery_review,
    ) -> str:
        reasons: list[str] = []
        if recovery_planner_result.requires_clarification:
            reasons.append("Planner requested clarification.")
        if not recovery_planner_result.action_plan.steps:
            reasons.append("Planner returned no recovery actions.")
        if not recovery_policy.approved:
            reasons.extend(f"{issue.code}: {issue.message}" for issue in recovery_policy.issues)
        if not recovery_review.approved:
            if recovery_review.rejection_reason:
                reasons.append(recovery_review.rejection_reason)
            reasons.extend(recovery_review.issues)
        return "Recovery plan was blocked. " + " ".join(reasons or ["No additional reason was provided."])
