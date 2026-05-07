from __future__ import annotations

import json

from ..models import DebugRunRecord, RecentTraceRecord, WorkflowTrace
from ..storage.recovery_events import RecoveryEventRecord
from .view_models import DebugRunSummary, RecentTraceSummary, RecoveryEventSummary


def summarize_recent_trace(record: RecentTraceRecord) -> RecentTraceSummary:
    return RecentTraceSummary(
        trace_id=record.trace_id,
        updated_at=record.updated_at,
        request=record.trace.request.user_request,
        status=record.status.value,
        risk_level=record.trace.policy_decision.risk_level.value,
    )


def recent_trace_label(summary: RecentTraceSummary) -> str:
    short_trace = summary.trace_id[:8]
    request = summary.request
    if len(request) > 28:
        request = f"{request[:25]}..."
    timestamp = summary.updated_at[5:16].replace("T", " ") if len(summary.updated_at) >= 16 else summary.updated_at
    return f"{timestamp} | {summary.status} | {summary.risk_level} | {request} | {short_trace}"


def summarize_debug_run(record: DebugRunRecord) -> DebugRunSummary:
    return DebugRunSummary(
        id=record.id,
        trace_id=record.trace_id,
        run_mode=record.run_mode.value,
        status=record.status.value,
        current_step=record.current_step,
        created_at=record.created_at or "",
        updated_at=record.updated_at or "",
        snapshot_text=debug_snapshot_to_plain_text(record.snapshot_json),
    )


def debug_run_label(summary: DebugRunSummary) -> str:
    short_id = summary.id[:8]
    timestamp = summary.created_at[5:16].replace("T", " ") if len(summary.created_at) >= 16 else summary.created_at
    return f"{timestamp} | {summary.run_mode} | step {summary.current_step} | {summary.status} | {short_id}"


def summarize_recovery_event(record: RecoveryEventRecord) -> RecoveryEventSummary:
    return RecoveryEventSummary(
        id=record.id,
        created_at=record.created_at,
        source=record.source,
        category=record.category,
        path=record.path,
        quarantined_path=record.quarantined_path,
        reason=record.reason,
    )


def recovery_event_label(summary: RecoveryEventSummary) -> str:
    timestamp = summary.created_at[5:16].replace("T", " ") if len(summary.created_at) >= 16 else summary.created_at
    source = {
        "todo_store": "待办",
        "workspace_draft_store": "草稿",
        "recipe_store": "方案",
        "prediction_store": "预测",
        "project_catalog_store": "项目",
        "activity_store": "活动",
        "activity_privacy_store": "隐私",
        "ui_state_store": "界面",
        "provider_config_store": "模型配置",
        "recovery_event_store": "恢复日志",
    }.get(summary.source, summary.source)
    return f"{timestamp} | {source} | {summary.category}"


def recovery_event_detail_text(summary: RecoveryEventSummary) -> str:
    return "\n".join(
        [
            f"恢复时间：{summary.created_at}",
            f"来源：{summary.source}",
            f"类别：{summary.category}",
            f"原文件：{summary.path}",
            f"隔离文件：{summary.quarantined_path}",
            f"原因：{summary.reason or '-'}",
        ]
    )


def debug_snapshot_to_plain_text(snapshot_json: dict) -> str:
    try:
        trace = WorkflowTrace.model_validate(snapshot_json)
    except Exception:  # noqa: BLE001 - snapshot viewer should remain best-effort
        return json.dumps(snapshot_json, ensure_ascii=False, indent=2)

    lines = [
        f"Trace: {trace.trace_id}",
        f"Workflow status: {trace.status.value}",
        f"Request: {trace.request.user_request}",
        "",
        "Planner",
        f"- Intent: {trace.planner_result.intent_summary}",
        f"- Plan: {trace.planner_result.action_plan.plan_name}",
        f"- Source: {trace.planner_result.action_plan.source}",
        f"- Risk guess: {trace.planner_result.risk_guess.value}",
        f"- Requires clarification: {trace.planner_result.requires_clarification}",
    ]
    if trace.timings:
        lines.append("- Timings:")
        lines.extend(f"  - {key}: {value}s" for key, value in sorted(trace.timings.items()))

    if trace.planner_result.intent_interpretation is not None:
        intent = trace.planner_result.intent_interpretation
        lines.extend(
            [
                f"- Intent template: {trace.planner_result.selected_intent_template or '-'}",
                f"- Planner template: {trace.planner_result.selected_planner_template or '-'}",
                "- Intent interpretation:",
                f"  - Primary intent: {intent.primary_intent}",
                f"  - Target kind: {intent.target_kind}",
                f"  - Target name: {intent.target_name}",
                f"  - Confidence: {intent.confidence}",
                f"  - Needs clarification: {intent.needs_clarification}",
            ]
        )
        if intent.clarification_question:
            lines.append(f"  - Clarification question: {intent.clarification_question}")

    lines.extend(
        [
            "",
            "Policy",
            f"- Approved: {trace.policy_decision.approved}",
            f"- Risk: {trace.policy_decision.risk_level.value}",
            f"- Requires confirmation: {trace.policy_decision.requires_user_confirmation}",
        ]
    )

    if trace.policy_decision.issues:
        lines.append("- Issues:")
        lines.extend(f"  - {issue.code}: {issue.message}" for issue in trace.policy_decision.issues)
    if trace.policy_decision.action_decisions:
        lines.append("- Action confirmations:")
        for decision in trace.policy_decision.action_decisions:
            lines.append(
                f"  - step {decision.step_index + 1}: {decision.action_type.value} "
                f"[{decision.risk_level.value}] confirm={decision.requires_confirmation} "
                f"whitelisted={decision.whitelisted}"
            )

    lines.extend(
        [
            "",
            "Reviewer",
            f"- Approved: {trace.review_result.approved}",
            f"- Risk: {trace.review_result.risk_level.value}",
            f"- Needs confirmation: {trace.review_result.needs_user_confirmation}",
            f"- Summary: {trace.review_result.review_summary}",
        ]
    )

    if trace.review_result.issues:
        lines.append("- Issues:")
        lines.extend(f"  - {issue}" for issue in trace.review_result.issues)

    if trace.recovery_events:
        lines.append("")
        lines.append("Recovery")
        lines.append(f"- Attempts: {trace.recovery_attempts}")
        for event in trace.recovery_events:
            lines.append(
                f"- step {event.failed_step_index + 1}: {event.recovery_status} "
                f"after {event.failed_action_type} -> {event.failed_target}; {event.message}"
            )
    if trace.prepare_error is not None:
        lines.append("")
        lines.append("Prepare error")
        lines.append(f"- Code: {trace.prepare_error.code}")
        lines.append(f"- Message: {trace.prepare_error.message}")
        if trace.prepare_error.remedy:
            lines.append(f"- Remedy: {trace.prepare_error.remedy}")
        if trace.prepare_error.details:
            lines.append(
                "- Details: "
                + json.dumps(trace.prepare_error.details, ensure_ascii=False, sort_keys=True)
            )

    lines.append("")
    lines.append("Planned actions")
    if trace.planner_result.action_plan.steps:
        for index, step in enumerate(trace.planner_result.action_plan.steps, start=1):
            lines.append(
                f"{index}. {step.action_type.value} -> {step.target} "
                f"[{step.risk_level.value}] {step.reason}"
            )
    else:
        lines.append("(No actions)")

    lines.append("")
    lines.append("Step results")
    if trace.step_results:
        for result in trace.step_results:
            elapsed = f" ({result.elapsed_seconds}s)" if result.elapsed_seconds is not None else ""
            lines.append(f"{result.step_index}. {result.status.value}{elapsed}: {result.message}")
            if result.metadata:
                lines.append(
                    "   Metadata: "
                    + json.dumps(result.metadata, ensure_ascii=False, sort_keys=True)
                )
            if result.diagnosis is not None:
                lines.append(f"   Failure code: {result.diagnosis.code}")
                if result.diagnosis.remedy:
                    lines.append(f"   Remedy: {result.diagnosis.remedy}")
                if result.diagnosis.details:
                    lines.append(
                        "   Details: "
                        + json.dumps(result.diagnosis.details, ensure_ascii=False, sort_keys=True)
                    )
    else:
        lines.append("(No executed steps)")

    return "\n".join(lines)
