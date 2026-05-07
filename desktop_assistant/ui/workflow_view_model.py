from __future__ import annotations

from ..models import WorkflowTrace
from .localization import (
    action_label,
    approval_label,
    bool_label,
    decision_state_label,
    execution_status_label,
    localized_text,
    plan_source_label,
    risk_label,
    timing_label,
    workflow_status_label,
)
from .view_models import ActionStepSummary, WorkflowSummary


def summarize_trace(trace: WorkflowTrace) -> WorkflowSummary:
    planner = trace.planner_result
    policy = trace.policy_decision
    review = trace.review_result
    prepare_error = trace.prepare_error
    results_by_step = {result.step_index: result for result in trace.step_results}
    decisions_by_step = {decision.step_index: decision for decision in policy.action_decisions}

    return WorkflowSummary(
        trace_id=trace.trace_id,
        status=trace.status.value,
        intent_summary=planner.intent_summary,
        plan_name=planner.action_plan.plan_name,
        plan_source=planner.action_plan.source,
        selected_intent_template=planner.selected_intent_template,
        selected_planner_template=planner.selected_planner_template,
        planner_risk=planner.risk_guess.value,
        timings=trace.timings,
        policy_approved=policy.approved,
        policy_risk=policy.risk_level.value,
        policy_requires_confirmation=policy.requires_user_confirmation,
        policy_issues=[f"{issue.code}: {issue.message}" for issue in policy.issues],
        review_approved=review.approved,
        review_risk=review.risk_level.value,
        review_needs_confirmation=review.needs_user_confirmation,
        review_summary=review.review_summary,
        review_issues=review.issues,
        requires_confirmation=policy.requires_user_confirmation or review.needs_user_confirmation,
        can_run_once=(
            policy.approved
            and review.approved
            and bool(planner.action_plan.steps)
            and trace.status.value not in {"completed", "failed", "stopped", "cancelled", "rejected"}
        ),
        decision_state=_decision_state(
            status=trace.status.value,
            policy_approved=policy.approved,
            review_approved=review.approved,
            requires_confirmation=policy.requires_user_confirmation or review.needs_user_confirmation,
            has_steps=bool(planner.action_plan.steps),
        ),
        prepare_error_code=prepare_error.code if prepare_error is not None else None,
        prepare_error_message=prepare_error.message if prepare_error is not None else None,
        prepare_error_stage=(
            str(prepare_error.details.get("stage") or "") if prepare_error is not None else None
        ),
        prepare_error_remedy=prepare_error.remedy if prepare_error is not None else None,
        steps=[
            ActionStepSummary(
                order=index + 1,
                action_type=step.action_type.value,
                target=step.target,
                risk_level=step.risk_level.value,
                reason=step.reason,
                requires_confirmation=(
                    decisions_by_step[index].requires_confirmation if index in decisions_by_step else False
                ),
                whitelisted=decisions_by_step[index].whitelisted if index in decisions_by_step else False,
                execution_status=results_by_step[index].status.value if index in results_by_step else None,
                execution_message=results_by_step[index].message if index in results_by_step else None,
                failure_code=(
                    results_by_step[index].diagnosis.code
                    if index in results_by_step and results_by_step[index].diagnosis is not None
                    else None
                ),
                failure_remedy=(
                    results_by_step[index].diagnosis.remedy
                    if index in results_by_step and results_by_step[index].diagnosis is not None
                    else None
                ),
                failure_details=(
                    results_by_step[index].diagnosis.details
                    if index in results_by_step and results_by_step[index].diagnosis is not None
                    else {}
                ),
                elapsed_seconds=results_by_step[index].elapsed_seconds if index in results_by_step else None,
                metadata=results_by_step[index].metadata if index in results_by_step else {},
            )
            for index, step in enumerate(planner.action_plan.steps)
        ],
    )


def summary_to_plain_text(summary: WorkflowSummary) -> str:
    lines = [
        f"追踪: {summary.trace_id}",
        f"状态: {workflow_status_label(summary.status)}",
        "",
        f"意图: {localized_text(summary.intent_summary)}",
        f"计划: {summary.plan_name}",
        f"计划来源: {plan_source_label(summary.plan_source)}",
        f"规划风险: {risk_label(summary.planner_risk)}",
        "",
        f"策略检查: {approval_label(summary.policy_approved)}",
        f"策略风险: {risk_label(summary.policy_risk)}",
        f"需要确认: {bool_label(summary.policy_requires_confirmation)}",
        f"决策状态: {decision_state_label(summary.decision_state)}",
    ]

    if summary.policy_issues:
        lines.append("策略问题:")
        lines.extend(f"- {localized_text(issue)}" for issue in summary.policy_issues)
    if summary.timings:
        lines.append("耗时:")
        lines.extend(f"- {timing_label(key)}: {value}s" for key, value in sorted(summary.timings.items()))
    if summary.prepare_error_code:
        lines.append("准备失败:")
        lines.append(f"- 阶段: {_prepare_stage_label(summary.prepare_error_stage)}")
        lines.append(f"- 原因: {localized_text(summary.prepare_error_message or '')}")
        if summary.prepare_error_remedy:
            lines.append(f"- 建议: {localized_text(summary.prepare_error_remedy)}")
        lines.append(f"- 代码: {summary.prepare_error_code}")

    lines.extend(
        [
            "",
            f"审查: {approval_label(summary.review_approved)}",
            f"审查风险: {risk_label(summary.review_risk)}",
            f"审查需要确认: {bool_label(summary.review_needs_confirmation)}",
            f"审查摘要: {localized_text(summary.review_summary)}",
        ]
    )

    if summary.review_issues:
        lines.append("审查问题:")
        lines.extend(f"- {localized_text(issue)}" for issue in summary.review_issues)

    lines.append("")
    lines.append("计划动作:")
    if summary.steps:
        for step in summary.steps:
            result = f" -> {execution_status_label(step.execution_status)}" if step.execution_status else ""
            elapsed = f" ({step.elapsed_seconds}s)" if step.elapsed_seconds is not None else ""
            confirmation = " 需确认" if step.requires_confirmation else ""
            trusted = " 已信任" if step.whitelisted else ""
            lines.append(
                f"{step.order}. {action_label(step.action_type)} -> {step.target} "
                f"[{risk_label(step.risk_level)}]{result}{elapsed}{confirmation}{trusted} {localized_text(step.reason)}"
            )
            if step.failure_code:
                lines.append(f"   失败代码: {step.failure_code}")
                if step.failure_remedy:
                    lines.append(f"   建议处理: {localized_text(step.failure_remedy)}")
    else:
        lines.append("(暂无动作)")

    return "\n".join(lines)


def _decision_state(
    *,
    status: str,
    policy_approved: bool,
    review_approved: bool,
    requires_confirmation: bool,
    has_steps: bool,
) -> str:
    if status == "completed":
        return "executed"
    if status == "failed":
        return "failed"
    if status == "stopped":
        return "stopped"
    if not policy_approved or not review_approved:
        return "blocked"
    if not has_steps:
        return "no_actions"
    if requires_confirmation:
        return "needs_confirmation"
    return "ready"


def _prepare_stage_label(value: str | None) -> str:
    return {
        "context": "上下文采样",
        "planner": "规划",
        "policy": "策略检查",
        "reviewer": "审查",
    }.get(value or "", value or "-")
