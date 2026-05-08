from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from ..confirmation import ConfirmationFlow, ConfirmationService
from ..habits import NextActionPrediction, NextActionPredictionStore
from ..habits.sampling import ActivitySamplingService
from ..input_router import InputRoute, InputRouter, InputRouteType
from ..models import ActionStep, ActionType, ExecutionStepResult, RiskLevel
from ..storage import RecoveryEventStore, recovery_notice_text
from ..todo import ReminderSettings, ReminderSettingsStore, TodoHomeStatus, TodoItem, TodoStore, TodoWorkspaceHint
from ..todo.models import TodoPriority, TodoTaskType
from ..todo.reminder_settings import logical_local_date
from ..recipe import WorkflowRecipe
from ..workspace import WorkspaceService, WorkspaceSuggestion
from .capability_view_model import capability_detail_to_plain_text
from .localization import action_label
from .view_models import CapabilitySummary


@dataclass(frozen=True)
class HomeShellSnapshot:
    home: TodoHomeStatus
    prediction: NextActionPrediction
    todos: list[TodoItem]
    recovery_notice: str = ""


class AssistantShellController:
    """Thin backend facade for the compact assistant shell."""

    def __init__(
        self,
        *,
        todo_store: TodoStore | None = None,
        prediction_store: NextActionPredictionStore | None = None,
        input_router: InputRouter | None = None,
        workspace_service: WorkspaceService | None = None,
        activity_service: ActivitySamplingService | None = None,
        confirmation_service: ConfirmationService | None = None,
        reminder_settings_store: ReminderSettingsStore | None = None,
        sync_service: object | None = None,
    ) -> None:
        self.todo_store = todo_store or TodoStore()
        self.reminder_settings_store = reminder_settings_store or ReminderSettingsStore()
        self.prediction_store = prediction_store or NextActionPredictionStore()
        self.input_router = input_router or InputRouter()
        self.workspace_service = workspace_service or WorkspaceService()
        self.activity_service = activity_service or ActivitySamplingService()
        self.confirmation_service = confirmation_service or ConfirmationService()
        self.recovery_event_store = RecoveryEventStore()
        self.sync_service = sync_service
        self._app_inventory_cache = None

    def snapshot(self) -> HomeShellSnapshot:
        todos = self.todo_store.list(include_done=False)
        return HomeShellSnapshot(
            home=self.todo_store.home_status(),
            prediction=self._load_prediction(),
            todos=todos,
            recovery_notice=recovery_notice_text(self.recovery_event_store.latest()),
        )

    def route_input(
        self,
        text: str,
        *,
        prediction: NextActionPrediction | None = None,
        accepted_prediction: bool = False,
    ) -> InputRoute:
        route = self.input_router.route(
            text,
            prediction=prediction or self._load_prediction(),
            accepted_prediction=accepted_prediction,
        )
        if route.route_type == InputRouteType.DIALOG and text.strip() and self.workspace_service.find_workspace_recipe(text):
            return InputRoute(
                route_type=InputRouteType.WORKSPACE,
                normalized_text=text.strip(),
                confidence="high",
                source="workspace_recipe",
                reason="matched saved workspace recipe",
            )
        return route

    def add_todo(
        self,
        title: str,
        *,
        description: str = "",
        important: bool = False,
        needs_computer: bool = False,
        priority: str | TodoPriority = TodoPriority.NORMAL,
        task_type: str | TodoTaskType = TodoTaskType.TEMPORARY,
        reminder_at: str | None = None,
        due_at: str | None = None,
    ) -> TodoItem:
        parsed_priority = _priority(priority)
        if important and parsed_priority == TodoPriority.NORMAL:
            parsed_priority = TodoPriority.HIGH
        item = self.todo_store.create(
            title,
            description=description,
            priority=parsed_priority,
            task_type=_task_type(task_type),
            important=important,
            needs_computer=needs_computer,
            reminder_at=reminder_at,
            due_at=due_at,
        )
        self._sync_push(item)
        return item

    def get_todo(self, item_id: str | None) -> TodoItem | None:
        return self.todo_store.get(item_id) if item_id else None

    def update_todo(
        self,
        item_id: str,
        *,
        title: str,
        description: str = "",
        important: bool = False,
        needs_computer: bool = False,
        priority: str | TodoPriority = TodoPriority.NORMAL,
        task_type: str | TodoTaskType | None = None,
        reminder_at: str | None = None,
    ) -> TodoItem | None:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Todo title cannot be empty.")
        changes: dict[str, object] = {
            "title": clean_title,
            "description": description.strip(),
            "priority": _priority(priority),
            "important": important,
            "needs_computer": needs_computer,
            "reminder_at": reminder_at,
        }
        if task_type is not None:
            changes["task_type"] = _task_type(task_type)
        item = self.todo_store.update(item_id, **changes)
        self._sync_push(item)
        return item

    def mark_todo_done(self, item_id: str) -> TodoItem | None:
        settings = self.reminder_settings()
        item = self.todo_store.mark_done(item_id, daily_completed_on=logical_local_date(datetime_now(), daily_reset_hour=settings.daily_reset_hour))
        self._sync_push(item)
        return item

    def postpone_todo(self, item_id: str, *, minutes: int | None = None) -> TodoItem | None:
        todo = self.todo_store.get(item_id)
        if todo is None:
            return None
        policy = self.reminder_settings().policy_for(todo)
        item = self.todo_store.postpone(item_id, minutes=minutes or policy.snooze_minutes)
        self._sync_push(item)
        return item

    def skip_todo_today(self, item_id: str) -> TodoItem | None:
        settings = self.reminder_settings()
        item = self.todo_store.skip_daily_today(item_id, daily_skipped_on=logical_local_date(datetime_now(), daily_reset_hour=settings.daily_reset_hour))
        self._sync_push(item)
        return item

    def delete_todo(self, item_id: str) -> bool:
        deleted = self.todo_store.delete(item_id)
        if deleted:
            self._sync_delete(item_id)
        return deleted

    def cancel_todo(self, item_id: str) -> TodoItem | None:
        item = self.todo_store.cancel(item_id)
        self._sync_push(item)
        return item

    def update_todo_workspace(
        self,
        item_id: str,
        *,
        workspace: TodoWorkspaceHint,
        needs_computer: bool,
    ) -> TodoItem | None:
        return self.todo_store.update_workspace(
            item_id,
            workspace=workspace,
            needs_computer=needs_computer,
        )

    def record_todo_execution(
        self,
        item_id: str,
        *,
        trace_id: str,
        status: str,
        message: str,
        executed_actions: list[dict[str, str]] | None = None,
    ) -> TodoItem | None:
        return self.todo_store.record_execution(
            item_id,
            trace_id=trace_id,
            status=status,
            message=message,
            executed_actions=executed_actions,
        )

    def record_todo_reminded(self, item_id: str, *, reminder_key: str) -> TodoItem | None:
        return self.todo_store.record_reminded(item_id, reminder_key=reminder_key)

    def reminder_settings(self) -> ReminderSettings:
        return self.reminder_settings_store.load()

    def save_reminder_settings(self, settings: ReminderSettings) -> ReminderSettings:
        return self.reminder_settings_store.save(settings)

    def confirm_todo_workspace(self, item_id: str, *, trusted_action_keys: list[str]) -> TodoItem | None:
        return self.todo_store.mark_workspace_confirmed(item_id, trusted_action_keys=trusted_action_keys)

    def workspace_from_goal(self, goal: str) -> WorkspaceSuggestion:
        suggestion = self.workspace_service.builder.from_goal(goal)
        return self.workspace_service.save_draft(suggestion)

    def workspace_recipe_for_goal(self, goal: str) -> WorkspaceSuggestion | None:
        return self.workspace_service.recipe_for_goal(goal)

    def workspace_from_todo(self, item_id: str) -> WorkspaceSuggestion | None:
        todo = self.todo_store.get(item_id)
        if todo is None:
            return None
        suggestion = self.workspace_service.builder.from_todo(todo)
        return self.workspace_service.save_draft(suggestion)

    def workspace_preview_from_todo(self, item_id: str) -> WorkspaceSuggestion | None:
        todo = self.todo_store.get(item_id)
        if todo is None:
            return None
        return self.workspace_service.builder.from_todo(todo)

    def build_confirmation_flow(self, suggestion: WorkspaceSuggestion) -> ConfirmationFlow:
        return self.confirmation_service.build_flow(suggestion.plan)

    def app_options(self, *, limit: int = 120) -> list[str]:
        inventory = self._load_app_inventory()
        if inventory is None:
            return []
        names = [app.name.strip() for app in inventory.applications if app.name.strip() and app.executable_path]
        unique = sorted(dict.fromkeys(names), key=str.lower)
        return unique[:limit]

    def resolve_app_name(self, text: str) -> str:
        target = text.strip()
        if not target:
            return ""
        inventory = self._load_app_inventory()
        if inventory is None:
            return target
        app = inventory.find(target)
        return app.name if app is not None else target

    def refine_workspace(
        self,
        suggestion: WorkspaceSuggestion,
        feedback: str,
    ) -> WorkspaceSuggestion:
        return self.workspace_service.refine(suggestion, feedback)

    def save_workspace_draft(self, suggestion: WorkspaceSuggestion) -> WorkspaceSuggestion:
        return self.workspace_service.save_draft(suggestion)

    def pending_workspace_draft(self, suggestion_id: str | None) -> WorkspaceSuggestion | None:
        return self.workspace_service.pending_draft(suggestion_id)

    def save_workspace_recipe(self, suggestion: WorkspaceSuggestion, *, name: str | None = None) -> WorkflowRecipe:
        return self.workspace_service.save_as_recipe(suggestion, name=name)

    def workspace_recipes(self) -> list[WorkflowRecipe]:
        return self.workspace_service.list_recipes()

    def workspace_from_recipe(self, recipe_id: str) -> WorkspaceSuggestion | None:
        return self.workspace_service.recipe_as_suggestion(recipe_id)

    def sample_activity_once(self) -> str:
        result = self.activity_service.tick()
        return result.message

    def refresh_app_inventory(self) -> str:
        store = self.workspace_service.builder.app_inventory_store
        inventory = store.ensure(refresh=True)
        self._app_inventory_cache = inventory
        return f"已刷新应用清单，共找到 {len(inventory.applications)} 个应用。"

    def capability_debug_text(self, action_type: ActionType | str | None = None) -> str:
        from ..tools.capability_debug import build_capability_debug_report

        wanted = action_type.value if isinstance(action_type, ActionType) else str(action_type or "")
        report = build_capability_debug_report()
        capabilities = [item for item in report.get("capabilities", []) if isinstance(item, dict)]
        if wanted:
            for item in capabilities:
                if item.get("action_type") == wanted:
                    return capability_detail_to_plain_text(CapabilitySummary.model_validate(item))
            return f"没有找到能力：{action_label(wanted)}。可以先刷新能力目录或检查 action_type。"
        total = int(report.get("total", 0) or 0)
        enabled = int(report.get("enabled", 0) or 0)
        missing = int(report.get("missing_handlers", 0) or 0)
        failures = int(report.get("recent_failures", 0) or 0)
        lines = [
            "能力状态概览",
            f"总能力：{total}",
            f"已启用：{enabled}",
            f"缺少 handler：{missing}",
            f"近期失败：{failures}",
        ]
        if report.get("storage_error"):
            lines.append(f"历史记录读取失败：{report['storage_error']}")
        return "\n".join(lines)

    def execute_direct_action(
        self,
        action_type: ActionType,
        target: str,
        *,
        params: dict | None = None,
        risk_level: RiskLevel = RiskLevel.LOW,
        reason: str = "用户在执行结果中选择了补救动作。",
    ) -> ExecutionStepResult:
        from ..adapters.windows_executor import WindowsExecutor

        action = ActionStep(
            action_type=action_type,
            target=target,
            params=params or {},
            risk_level=risk_level,
            reason=reason,
        )
        return WindowsExecutor().execute(action, 0, f"remedy-{uuid4()}")

    def _sync_push(self, item: TodoItem | None) -> None:
        if item is None or self.sync_service is None:
            return
        threading.Thread(target=self._sync_push_worker, args=(item,), daemon=True).start()

    def _sync_push_worker(self, item: TodoItem) -> None:
        try:
            self.sync_service.push_item(item)
        except Exception:
            pass

    def _sync_delete(self, item_id: str) -> None:
        if self.sync_service is None:
            return
        threading.Thread(target=self._sync_delete_worker, args=(item_id,), daemon=True).start()

    def _sync_delete_worker(self, item_id: str) -> None:
        try:
            self.sync_service.delete_item(item_id)
        except Exception:
            pass

    def sync_todos(self) -> dict:
        if self.sync_service is None:
            return {"error": "sync not configured"}
        local_items = self.todo_store.load()
        merged, stats = self.sync_service.full_sync(local_items)
        if stats.get("skipped"):
            return stats
        delete_ids = stats.get("deleted_count", 0)
        if delete_ids:
            for item in local_items:
                if item.id not in {m.id for m in merged}:
                    self.todo_store.delete(item.id)
        self.todo_store.save(merged)
        return stats

    def _load_prediction(self) -> NextActionPrediction:
        try:
            return self.prediction_store.load()
        except Exception as exc:  # noqa: BLE001 - UI should show a usable fallback.
            prediction = NextActionPrediction.empty()
            prediction.reasons = [f"Prediction unavailable: {type(exc).__name__}: {exc}"]
            return prediction

    def _load_app_inventory(self):  # type: ignore[no-untyped-def]
        if self._app_inventory_cache is not None:
            return self._app_inventory_cache
        store = self.workspace_service.builder.app_inventory_store
        try:
            if getattr(store, "path", None) is not None and store.path.exists():
                self._app_inventory_cache = store.load()
            else:
                self._app_inventory_cache = store.ensure(refresh=False)
            return self._app_inventory_cache
        except Exception:  # noqa: BLE001 - app choices are optional UI help.
            return None


def _priority(value: str | TodoPriority) -> TodoPriority:
    if isinstance(value, TodoPriority):
        return value
    try:
        return TodoPriority(str(value))
    except ValueError:
        return TodoPriority.NORMAL


def _task_type(value: str | TodoTaskType) -> TodoTaskType:
    if isinstance(value, TodoTaskType):
        return value
    try:
        return TodoTaskType(str(value))
    except ValueError:
        return TodoTaskType.TEMPORARY


def datetime_now() -> datetime:
    return datetime.now(UTC)
