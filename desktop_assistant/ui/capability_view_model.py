from __future__ import annotations

import json

from ..capabilities import CapabilityDefinition, CapabilityRegistry
from ..models import RecentTraceRecord
from .localization import action_label, localized_text, risk_label
from .view_models import CapabilitySummary


def summarize_capability_registry(
    registry: CapabilityRegistry,
    *,
    catalog_path: str = "",
    available_handler_names: set[str] | None = None,
    recent_traces: list[RecentTraceRecord] | None = None,
) -> list[CapabilitySummary]:
    failures_by_action = _recent_failures_by_action(recent_traces or [])
    return [
        summarize_capability(
            capability,
            catalog_path=catalog_path,
            available_handler_names=available_handler_names,
            recent_failure=failures_by_action.get(capability.action_type.value),
        )
        for capability in registry.all_capabilities()
    ]


def summarize_capability(
    capability: CapabilityDefinition,
    *,
    catalog_path: str = "",
    available_handler_names: set[str] | None = None,
    recent_failure: dict | None = None,
) -> CapabilitySummary:
    handler_status, handler_available = _handler_status(
        capability.execution_mode,
        capability.handler_name,
        available_handler_names,
    )
    recent_count = int((recent_failure or {}).get("count", 0))
    return CapabilitySummary(
        action_type=capability.action_type.value,
        title=capability.title,
        description=capability.description,
        execution_mode=capability.execution_mode,
        handler_name=capability.handler_name or "-",
        handler_status=handler_status,
        handler_available=handler_available,
        default_risk=capability.default_risk.value,
        enabled=capability.execution_mode != "disabled",
        target_schema=capability.target_schema,
        params_schema=capability.params_schema,
        safety_rules=list(capability.safety_rules),
        planner_guidance=list(capability.planner_guidance),
        catalog_path=catalog_path,
        recent_failure_count=recent_count,
        recent_failure_code=(recent_failure or {}).get("code"),
        recent_failure_message=(recent_failure or {}).get("message"),
        recent_failure_remedy=(recent_failure or {}).get("remedy"),
        recent_failure_trace_id=(recent_failure or {}).get("trace_id"),
        recent_failure_updated_at=(recent_failure or {}).get("updated_at"),
        health_label=_health_label(capability.execution_mode, handler_status, recent_count),
        risk_explanation=_risk_explanation(capability.default_risk.value),
        test_hint=_test_hint(capability.action_type.value, handler_status),
    )


def capability_label(summary: CapabilitySummary) -> str:
    state = "启用" if summary.enabled else "停用"
    failure = f" | 近期待处理:{summary.recent_failure_count}" if summary.recent_failure_count else ""
    return (
        f"{action_label(summary.action_type)} | {state} | "
        f"{risk_label(summary.default_risk)} | {summary.health_label or _handler_status_label(summary.handler_status)}"
        f"{failure}"
    )


def capability_detail_to_plain_text(summary: CapabilitySummary) -> str:
    lines = [
        f"能力：{action_label(summary.action_type)}",
        f"标题：{localized_text(summary.title)}",
        f"状态：{'已启用' if summary.enabled else '已停用'}",
        f"执行方式：{summary.execution_mode}",
        f"Handler：{summary.handler_name}",
        f"Handler 状态：{_handler_status_label(summary.handler_status)}",
        f"健康状态：{summary.health_label or '-'}",
        f"默认风险：{risk_label(summary.default_risk)}",
        f"风险说明：{summary.risk_explanation}",
        f"调试建议：{summary.test_hint}",
        f"目录：{summary.catalog_path or '-'}",
        f"近期失败：{summary.recent_failure_count}",
    ]
    if summary.recent_failure_code:
        lines.extend(
            [
                f"最近失败代码：{summary.recent_failure_code}",
                f"Trace：{summary.recent_failure_trace_id or '-'}",
                f"时间：{summary.recent_failure_updated_at or '-'}",
                f"说明：{localized_text(summary.recent_failure_message or '-')}",
                f"建议：{localized_text(summary.recent_failure_remedy or '-')}",
            ]
        )
    lines.extend(
        [
            "",
            "说明",
            localized_text(summary.description or "-"),
            "",
            "目标格式",
            json.dumps(summary.target_schema, ensure_ascii=False, indent=2),
            "",
            "参数格式",
            json.dumps(summary.params_schema, ensure_ascii=False, indent=2),
            "",
            "安全规则",
        ]
    )
    lines.extend(f"- {localized_text(rule)}" for rule in summary.safety_rules) if summary.safety_rules else lines.append("-")
    lines.append("")
    lines.append("规划提示")
    lines.extend(f"- {localized_text(item)}" for item in summary.planner_guidance) if summary.planner_guidance else lines.append("-")
    return "\n".join(lines)


def _handler_status(
    execution_mode: str,
    handler_name: str,
    available_handler_names: set[str] | None,
) -> tuple[str, bool]:
    if execution_mode == "disabled":
        return "disabled", False
    if not handler_name:
        return "missing_handler_name", False
    if handler_name == "simulated":
        return "simulated", True
    if available_handler_names is None:
        return "not_checked", False
    if handler_name in available_handler_names:
        return "available", True
    return "missing", False


def _handler_status_label(value: str) -> str:
    return {
        "disabled": "已停用",
        "missing_handler_name": "缺少 handler 名称",
        "simulated": "模拟能力",
        "not_checked": "尚未检查",
        "available": "可用",
        "missing": "未接入",
    }.get(value, value)


def _health_label(execution_mode: str, handler_status: str, recent_failure_count: int) -> str:
    if execution_mode == "disabled":
        return "已停用"
    if handler_status == "missing":
        return "需要接 handler"
    if recent_failure_count:
        return "最近有失败"
    if handler_status in {"available", "simulated"}:
        return "可测试"
    return _handler_status_label(handler_status)


def _risk_explanation(value: str) -> str:
    return {
        "low": "低风险动作通常可直接执行，不应打扰用户。",
        "medium": "中风险动作执行前需要明确确认，可进入动作级白名单。",
        "high": "高风险动作需要谨慎确认，默认不建议长期信任。",
        "critical": "严重风险动作应阻止或拆成更安全的步骤。",
    }.get(value, "使用能力目录中的默认风险。")


def _test_hint(action_type: str, handler_status: str) -> str:
    if handler_status == "missing":
        return "先接入真实 handler，再做 UI 测试。"
    return {
        "open_app": "输入一个已安装应用名称，确认能打开并能反馈失败原因。",
        "focus_app": "先打开目标应用，再测试能否聚焦窗口。",
        "answer_query": "输入天气、价格等问题，检查答案、来源和置信度。",
        "list_windows": "刷新窗口列表，确认能看到标题、状态和程序位置。",
    }.get(action_type, "用一个低风险目标做 dry-run，再执行一次确认结果。")


def _recent_failures_by_action(records: list[RecentTraceRecord]) -> dict[str, dict]:
    failures: dict[str, dict] = {}
    for record in records:
        for result in record.trace.step_results:
            if result.status.value != "failed":
                continue
            action_type = result.action.action_type.value
            entry = failures.setdefault(action_type, {"count": 0})
            entry["count"] += 1
            if "code" not in entry:
                entry["code"] = result.diagnosis.code if result.diagnosis is not None else None
                entry["message"] = result.message
                entry["remedy"] = result.diagnosis.remedy if result.diagnosis is not None else None
                entry["trace_id"] = record.trace_id
                entry["updated_at"] = record.updated_at
    return failures
