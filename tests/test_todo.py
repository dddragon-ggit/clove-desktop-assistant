from __future__ import annotations

import unittest
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from shutil import rmtree
from unittest.mock import patch
from uuid import uuid4

from desktop_assistant.todo import (
    TodoItem,
    TodoPriority,
    ReminderPolicy,
    ReminderSettings,
    TodoStatus,
    TodoTaskType,
    TodoStore,
    TodoUrgency,
    TodoWorkspaceHint,
    build_home_status,
    default_todo_database_path,
    due_todo_reminders,
    parse_todo_time,
    workspace_hint_from_plan,
)
from desktop_assistant.todo.reminder_settings import reminder_policy_key
from desktop_assistant.models import ActionPlan, ActionStep, ActionType
from desktop_assistant.adapters.todo_actions import CreateReminderHandler, ShowTasksHandler


def _workspace_path() -> Path:
    base = Path.cwd() / "runtime" / "test_todo"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


class TodoStoreTests(unittest.TestCase):
    def test_create_update_complete_and_delete_todo(self) -> None:
        root = _workspace_path()
        try:
            store = TodoStore(root / "todos.json")
            item = store.create(
                "写周报",
                priority=TodoPriority.HIGH,
                needs_computer=True,
                workspace=TodoWorkspaceHint(apps=["Cursor"], projects=["desktop_assistant"]),
            )

            self.assertEqual(store.get(item.id).title, "写周报")
            self.assertEqual(store.list()[0].workspace.apps, ["Cursor"])

            updated = store.update(item.id, title="写本周周报")
            self.assertEqual(updated.title, "写本周周报")

            done = store.mark_done(item.id)
            self.assertEqual(done.status, TodoStatus.DONE)
            self.assertEqual(store.list(), [])

            cancelled = store.cancel(item.id)
            self.assertEqual(cancelled.status, TodoStatus.CANCELLED)

            self.assertTrue(store.delete(item.id))
        finally:
            rmtree(root, ignore_errors=True)

    def test_todo_task_type_and_reminder_state_are_persisted(self) -> None:
        root = _workspace_path()
        try:
            store = TodoStore(root / "todos.json")
            item = store.create(
                "daily standup",
                task_type=TodoTaskType.DAILY,
                reminder_at="2026-05-04T09:00:00+00:00",
            )

            store.record_reminded(item.id, reminder_key="daily:test:2026-05-04")
            loaded = store.get(item.id)

            self.assertEqual(loaded.task_type, TodoTaskType.DAILY)
            self.assertEqual(loaded.last_reminder_key, "daily:test:2026-05-04")
            self.assertTrue(loaded.last_reminded_at)
        finally:
            rmtree(root, ignore_errors=True)

    def test_daily_task_completion_stays_visible_as_today_done(self) -> None:
        root = _workspace_path()
        try:
            store = TodoStore(root / "todos.json")
            daily = store.create("daily review", task_type=TodoTaskType.DAILY)
            temporary = store.create("one-off review", task_type=TodoTaskType.TEMPORARY)

            completed_daily = store.mark_done(daily.id)
            completed_temporary = store.mark_done(temporary.id)

            self.assertEqual(completed_daily.status, TodoStatus.OPEN)
            self.assertTrue(completed_daily.is_daily_completed_today())
            self.assertEqual(completed_temporary.status, TodoStatus.DONE)
            self.assertEqual([item.id for item in store.list()], [daily.id])
        finally:
            rmtree(root, ignore_errors=True)

    def test_due_todo_reminders_dedupes_temporary_and_daily_tasks(self) -> None:
        now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
        temporary = TodoItem(title="temporary", reminder_at="2026-05-04T09:30:00+00:00")
        daily = TodoItem(title="daily", task_type=TodoTaskType.DAILY, reminder_at="2026-04-30T09:00:00+00:00")
        already_reminded = TodoItem(
            title="already daily",
            task_type=TodoTaskType.DAILY,
            reminder_at="2026-04-30T08:00:00+00:00",
            last_reminder_key="daily:already:2026-05-04",
        )
        already_reminded.id = "already"

        reminders = due_todo_reminders([temporary, daily, already_reminded], now=now)

        self.assertEqual([reminder.todo.title for reminder in reminders], ["temporary", "daily"])
        self.assertTrue(reminders[0].reminder_key.startswith(f"temporary:{temporary.id}:"))
        self.assertEqual(reminders[1].reminder_key, f"daily:{daily.id}:2026-05-04:09:00")

    def test_due_todo_reminders_skip_daily_completed_today(self) -> None:
        now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
        daily = TodoItem(
            title="daily",
            task_type=TodoTaskType.DAILY,
            reminder_at="2026-04-30T09:00:00+00:00",
            daily_completed_on="2026-05-04",
        )

        self.assertEqual(due_todo_reminders([daily], now=now), [])

    def test_due_todo_reminders_support_snooze_repeat_quiet_hours_and_skip_today(self) -> None:
        now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
        snoozed = TodoItem(
            title="snoozed",
            reminder_at="2026-05-04T09:00:00+00:00",
            snoozed_until="2026-05-04T09:50:00+00:00",
        )
        repeat = TodoItem(
            title="repeat",
            reminder_at="2026-05-04T09:00:00+00:00",
            last_reminder_key="temporary:repeat:2026-05-04T09:00:00+00:00",
            last_reminded_at="2026-05-04T09:20:00+00:00",
        )
        repeat.id = "repeat"
        skipped = TodoItem(
            title="skipped",
            task_type=TodoTaskType.DAILY,
            reminder_at="2026-05-04T08:00:00+00:00",
            daily_skipped_on="2026-05-04",
        )

        reminders = due_todo_reminders([snoozed, repeat, skipped], now=now)

        self.assertEqual([reminder.todo.title for reminder in reminders], ["snoozed", "repeat"])
        self.assertEqual([reminder.kind for reminder in reminders], ["snoozed", "repeat"])
        self.assertEqual(due_todo_reminders([snoozed], now=now, quiet_hours=(time(0, 0), time(23, 59))), [])

    def test_due_todo_reminders_use_global_policy_matrix(self) -> None:
        now = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
        repeat = TodoItem(
            title="urgent temporary",
            priority=TodoPriority.URGENT,
            reminder_at="2026-05-04T09:00:00+00:00",
            last_reminder_key="temporary:urgent:2026-05-04T09:00:00+00:00",
            last_reminded_at="2026-05-04T09:45:00+00:00",
        )
        repeat.id = "urgent"
        settings = ReminderSettings(
            quiet_enabled=False,
            policies={
                reminder_policy_key(TodoTaskType.TEMPORARY, TodoPriority.URGENT): ReminderPolicy(
                    repeat_enabled=True,
                    repeat_minutes=10,
                    max_repeats=2,
                    snooze_minutes=7,
                )
            },
        )

        reminders = due_todo_reminders([repeat], now=now, settings=settings)

        self.assertEqual([reminder.todo.id for reminder in reminders], ["urgent"])
        self.assertEqual(reminders[0].kind, "repeat")
        self.assertEqual(settings.policy_for(repeat).snooze_minutes, 7)

    def test_daily_reminder_completion_uses_configured_reset_hour(self) -> None:
        local_tz = datetime.now().astimezone().tzinfo
        now = datetime(2026, 5, 4, 2, 0, tzinfo=local_tz)
        daily = TodoItem(
            title="daily review",
            task_type=TodoTaskType.DAILY,
            reminder_at="2026-05-01T01:00:00+00:00",
            daily_completed_on="2026-05-03",
        )
        settings = ReminderSettings(quiet_enabled=False, daily_reset_hour=4)

        self.assertEqual(due_todo_reminders([daily], now=now, settings=settings), [])

    def test_default_sqlite_store_does_not_reimport_legacy_json_after_delete(self) -> None:
        root = _workspace_path()
        try:
            legacy_store = TodoStore(root / "data" / "todos.json")
            legacy_item = legacy_store.create("旧待办")

            store = TodoStore(root / "data" / "desktop_assistant.db")
            store._legacy_json_path = root / "data" / "todos.json"

            self.assertEqual([item.id for item in store.list()], [legacy_item.id])
            self.assertTrue(store.delete(legacy_item.id))
            self.assertEqual(store.list(), [])

            reloaded = TodoStore(root / "data" / "desktop_assistant.db")
            reloaded._legacy_json_path = root / "data" / "todos.json"

            self.assertEqual(reloaded.list(), [])
        finally:
            rmtree(root, ignore_errors=True)

    def test_default_sqlite_delete_removes_matching_legacy_json_item(self) -> None:
        root = _workspace_path()
        try:
            legacy_store = TodoStore(root / "data" / "todos.json")
            legacy_item = legacy_store.create("旧待办")

            store = TodoStore(root / "data" / "desktop_assistant.db")
            store._legacy_json_path = root / "data" / "todos.json"

            self.assertEqual([item.id for item in store.list()], [legacy_item.id])
            self.assertTrue(store.delete(legacy_item.id))

            self.assertEqual(store.list(), [])
            self.assertEqual(legacy_store.list(include_done=True), [])
        finally:
            rmtree(root, ignore_errors=True)

    def test_default_store_uses_sqlite_database_path(self) -> None:
        store = TodoStore()
        self.assertEqual(store.path, default_todo_database_path())
        self.assertTrue(str(store.path).endswith(".db"))

    def test_home_status_colors_follow_nearest_open_task_time(self) -> None:
        now = datetime(2026, 4, 30, 9, 0, tzinfo=UTC)
        red_item = _item("马上开会", now + timedelta(minutes=20))
        orange_item = _item("三小时内", now + timedelta(minutes=120))
        yellow_item = _item("以后处理", now + timedelta(hours=5))

        self.assertEqual(build_home_status([red_item], now=now).urgency, TodoUrgency.RED)
        self.assertEqual(build_home_status([orange_item], now=now).urgency, TodoUrgency.ORANGE)
        self.assertEqual(build_home_status([yellow_item], now=now).urgency, TodoUrgency.YELLOW)
        self.assertEqual(build_home_status([], now=now).urgency, TodoUrgency.GREEN)

    def test_home_status_counts_important_open_items(self) -> None:
        now = datetime(2026, 4, 30, 7, 0, tzinfo=UTC)
        normal = _item("普通任务", None)
        important = _item("重要任务", None, priority=TodoPriority.HIGH)
        done = _item("完成任务", None, priority=TodoPriority.URGENT)
        done.status = TodoStatus.DONE

        status = build_home_status([normal, important, done], now=now)

        self.assertEqual(status.greeting, "下午好")
        self.assertEqual(status.important_open_count, 1)
        self.assertEqual(status.open_count, 2)
        self.assertEqual(status.urgency, TodoUrgency.YELLOW)

    def test_postpone_and_execution_record_are_persisted(self) -> None:
        root = _workspace_path()
        try:
            store = TodoStore(root / "todos.json")
            item = store.create("复盘", reminder_at="2026-04-30T09:00:00+00:00")

            postponed = store.postpone(item.id, minutes=30)
            recorded = store.record_execution(
                item.id,
                trace_id="trace-1",
                status="completed",
                message="ok",
                executed_actions=[{"action_type": "open_url", "target": "https://example.com"}],
            )
            confirmed = store.mark_workspace_confirmed(item.id, trusted_action_keys=["abc"])

            self.assertIsNotNone(postponed.snoozed_until)
            self.assertGreater(datetime.fromisoformat(postponed.snoozed_until), datetime.now(UTC))
            self.assertEqual(recorded.last_execution.trace_id, "trace-1")
            self.assertEqual(recorded.last_execution.executed_actions[0]["target"], "https://example.com")
            self.assertTrue(confirmed.workspace_confirmed)
            self.assertEqual(confirmed.trusted_action_keys, ["abc"])
        finally:
            rmtree(root, ignore_errors=True)

    def test_update_preserves_workspace_and_last_execution(self) -> None:
        root = _workspace_path()
        try:
            store = TodoStore(root / "todos.json")
            item = store.create(
                "准备项目",
                workspace=TodoWorkspaceHint(apps=["Cursor"], urls=["https://example.com"]),
            )
            store.record_execution(item.id, trace_id="trace-1", status="success", message="opened")

            updated = store.update(
                item.id,
                title="准备项目文档",
                description="补充说明",
                priority=TodoPriority.HIGH,
                reminder_at="2026-05-01T09:00:00+00:00",
            )

            self.assertEqual(updated.title, "准备项目文档")
            self.assertEqual(updated.description, "补充说明")
            self.assertEqual(updated.workspace.apps, ["Cursor"])
            self.assertEqual(updated.workspace.urls, ["https://example.com"])
            self.assertEqual(updated.last_execution.trace_id, "trace-1")
            self.assertEqual(updated.last_execution.status, "success")
        finally:
            rmtree(root, ignore_errors=True)

    def test_workspace_binding_from_plan_and_store_update(self) -> None:
        root = _workspace_path()
        try:
            store = TodoStore(root / "todos.json")
            item = store.create("准备工作区", workspace=TodoWorkspaceHint(apps=["OldApp"]))
            store.record_execution(item.id, trace_id="trace-1", status="success", message="ok")
            store.mark_workspace_confirmed(item.id, trusted_action_keys=["old-trust"])
            plan = ActionPlan(
                plan_name="workspace",
                source="test",
                steps=[
                    ActionStep(action_type=ActionType.OPEN_APP, target="Cursor"),
                    ActionStep(action_type=ActionType.FOCUS_APP, target="Cursor"),
                    ActionStep(action_type=ActionType.OPEN_URL, target="https://example.com"),
                    ActionStep(action_type=ActionType.OPEN_PROJECT, target="desktop_assistant"),
                ],
            )

            updated = store.update_workspace(
                item.id,
                workspace=workspace_hint_from_plan(plan),
                needs_computer=True,
            )

            self.assertEqual(updated.workspace.apps, ["Cursor"])
            self.assertEqual(updated.workspace.urls, ["https://example.com"])
            self.assertEqual(updated.workspace.projects, ["desktop_assistant"])
            self.assertTrue(updated.needs_computer)
            self.assertFalse(updated.workspace_confirmed)
            self.assertEqual(updated.trusted_action_keys, [])
            self.assertEqual(updated.last_execution.trace_id, "trace-1")
        finally:
            rmtree(root, ignore_errors=True)

    def test_todo_handlers_use_real_todo_store(self) -> None:
        root = _workspace_path()
        try:
            store = TodoStore(root / "todos.json")
            create_result = CreateReminderHandler(store).execute(
                ActionStep(action_type=ActionType.CREATE_REMINDER, target="喝水", params={"minutes": 10}),
                0,
                "trace",
            )
            show_result = ShowTasksHandler(store).execute(
                ActionStep(action_type=ActionType.SHOW_TASKS, target="today"),
                1,
                "trace",
            )

            self.assertEqual(create_result.metadata["todo"]["title"], "喝水")
            self.assertEqual(show_result.metadata["count"], 1)
            self.assertEqual(show_result.metadata["todos"][0]["title"], "喝水")
        finally:
            rmtree(root, ignore_errors=True)

    def test_save_keeps_existing_json_when_atomic_replace_fails(self) -> None:
        root = _workspace_path()
        try:
            path = root / "todos.json"
            path.write_text('{"todos":[{"id":"1","title":"old","status":"open","priority":"normal"}]}', encoding="utf-8")
            store = TodoStore(path)
            item = TodoItem(title="新任务")

            with patch("desktop_assistant.storage.json_files.os.replace", side_effect=OSError("disk busy")):
                with self.assertRaises(OSError):
                    store.save([item])

            self.assertIn('"title":"old"', path.read_text(encoding="utf-8").replace(" ", "").replace("\n", ""))
        finally:
            rmtree(root, ignore_errors=True)

    def test_load_quarantines_corrupted_todo_json_and_recovers_empty_list(self) -> None:
        root = _workspace_path()
        try:
            path = root / "todos.json"
            path.write_text("{not-json", encoding="utf-8")

            store = TodoStore(path)
            loaded = store.load()

            self.assertEqual(loaded, [])
            self.assertFalse(path.exists())
            quarantined = list(root.glob("todos.json.corrupt*"))
            self.assertEqual(len(quarantined), 1)
        finally:
            rmtree(root, ignore_errors=True)

    def test_parse_todo_time_accepts_relative_and_clock_inputs(self) -> None:
        now = datetime(2026, 4, 30, 9, 0, tzinfo=UTC)

        self.assertIn("09:30", parse_todo_time("30m", now=now))
        self.assertIn("10:00", parse_todo_time("1小时", now=now))
        self.assertIn("11:20", parse_todo_time("11:20", now=now))
        self.assertIsNone(parse_todo_time("不确定", now=now))


def _item(title: str, when: datetime | None, priority: TodoPriority = TodoPriority.NORMAL):
    from desktop_assistant.todo import TodoItem

    return TodoItem(
        title=title,
        priority=priority,
        reminder_at=when.isoformat() if when else None,
    )


if __name__ == "__main__":
    unittest.main()
