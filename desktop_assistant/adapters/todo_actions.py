from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from ..capability.executor import execution_failed, execution_success
from ..models import ActionStep, ActionType, ExecutionStepResult
from ..todo import TodoPriority, TodoStore


class ShowTasksHandler:
    action_type = ActionType.SHOW_TASKS
    handler_name = "todo.show_tasks"

    def __init__(self, todo_store: TodoStore | None = None) -> None:
        self.todo_store = todo_store or TodoStore()

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        include_done = bool(action.params.get("include_done", False))
        items = self.todo_store.list(include_done=include_done)
        status = self.todo_store.home_status()
        important = [item for item in items if item.is_important() and item.is_open()]
        return execution_success(
            action,
            step_index,
            f"[{trace_id}] Listed {len(items)} todo item(s); {len(important)} important open item(s).",
            metadata={
                "todos": [item.model_dump(mode="json") for item in items],
                "home_status": status.model_dump(mode="json"),
                "count": len(items),
                "important_open_count": len(important),
            },
        )


class CreateReminderHandler:
    action_type = ActionType.CREATE_REMINDER
    handler_name = "todo.create_reminder"

    def __init__(self, todo_store: TodoStore | None = None) -> None:
        self.todo_store = todo_store or TodoStore()

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        title = str(action.params.get("title") or action.target).strip()
        if not title:
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Cannot create reminder without a title.",
                code="TODO_TITLE_EMPTY",
                details={"target": action.target, "params": action.params},
                remedy="Provide reminder text or a title parameter.",
            )

        minutes = _minutes(action)
        reminder_at = None
        if minutes is not None:
            reminder_at = (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()
        item = self.todo_store.create(
            title,
            description=str(action.params.get("description") or ""),
            priority=_priority(action),
            important=bool(action.params.get("important", False)),
            needs_computer=bool(action.params.get("needs_computer", False)),
            due_at=_string_or_none(action.params.get("due_at")),
            reminder_at=_string_or_none(action.params.get("reminder_at")) or reminder_at,
        )
        return execution_success(
            action,
            step_index,
            f"[{trace_id}] Created reminder: {item.title}",
            metadata={"todo": item.model_dump(mode="json")},
        )


def _minutes(action: ActionStep) -> int | None:
    raw = action.params.get("minutes")
    if raw not in (None, ""):
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return None
    match = re.fullmatch(r"\s*(\d+)\s*(?:m|min|minutes|分钟)?\s*", action.target, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _priority(action: ActionStep) -> TodoPriority:
    raw = str(action.params.get("priority") or TodoPriority.NORMAL.value)
    try:
        return TodoPriority(raw)
    except ValueError:
        return TodoPriority.NORMAL


def _string_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
