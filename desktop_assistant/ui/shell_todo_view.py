from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..models import ActionStep
from ..todo import TodoItem
from ..workspace import WorkspaceSuggestion
from . import shell_text as text
from .localization import action_label, execution_status_label, risk_label
from .shell_workspace_view import compact_workspace_action_lines


def todo_detail_text(todo: TodoItem, suggestion: WorkspaceSuggestion | None, confirmation: str = "") -> str:
    messages = [confirmation] if confirmation else []
    if todo.last_execution is not None:
        messages.append(
            text.TODO_EXECUTION_RESULT.format(
                status=execution_status_label(todo.last_execution.status),
                message=todo.last_execution.message,
            )
        )
        if todo.last_execution.executed_actions:
            messages.append(text.TODO_FINAL_ACTIONS.format(actions=_executed_actions_text(todo.last_execution.executed_actions)))
    return text.todo_detail_text(
        title=todo.title,
        priority=f"{_task_type_label(todo.task_type.value)} | {text.priority_label(todo.priority.value, important=todo.is_important())}",
        time_text=todo_short_time(todo.next_time()),
        description=todo.description,
        actions=compact_workspace_action_lines(suggestion),
        execution_message="\n".join(messages),
        workspace_sentence=_workspace_sentence(suggestion),
    )


def todo_confirmation_message(controller, suggestion: WorkspaceSuggestion | None) -> str:  # type: ignore[no-untyped-def]
    if suggestion is None or not suggestion.plan.steps:
        return ""
    flow = controller.build_confirmation_flow(suggestion)
    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    risk = max((card.risk_level for card in flow.action_cards), key=lambda value: risk_order.get(value, 0), default="low")
    return text.todo_confirmation_text(
        approved=flow.approved_by_policy,
        action_count=len(suggestion.plan.steps),
        risk=risk_label(risk),
    )


def todo_short_time(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return value
    return parsed.strftime("%m-%d %H:%M")


def todo_editable_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M")


def _task_type_label(task_type: str) -> str:
    return text.TODO_DAILY_TASK if task_type == "daily" else text.TODO_TEMPORARY_TASK


def _executed_actions_text(actions: list[dict[str, str]]) -> str:
    lines = []
    for index, action in enumerate(actions, 1):
        label = action_label(action.get("action_type", ""))
        status = execution_status_label(action.get("status", ""))
        suffix = f"（{status}）" if status else ""
        lines.append(f"{index}. {label}：{action.get('target', '')}{suffix}")
    return "\n".join(lines)


def _workspace_sentence(suggestion: WorkspaceSuggestion | None) -> str:
    if suggestion is None or not suggestion.plan.steps:
        return ""
    parts = [_natural_action(step) for step in suggestion.plan.steps[:3]]
    clean_parts = [part for part in parts if part]
    if not clean_parts:
        return ""
    suffix = "等资源" if len(suggestion.plan.steps) > 3 else ""
    return f"建议先{'、'.join(clean_parts)}{suffix}，要现在准备吗？"


def _natural_action(step: ActionStep) -> str:
    target = _target_title(step)
    return {
        "open_app": f"打开 {target}",
        "focus_app": f"切到 {target}",
        "open_url": f"打开网页 {target}",
        "open_file": f"打开文件 {target}",
        "open_folder": f"打开文件夹 {target}",
        "open_project": f"打开项目 {target}",
    }.get(step.action_type.value, f"{action_label(step.action_type.value)} {target}")


def _target_title(step: ActionStep) -> str:
    if step.action_type.value in {"open_file", "open_folder", "open_project"}:
        return Path(step.target).name or step.target
    return step.target
