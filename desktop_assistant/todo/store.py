from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..storage import quarantine_corrupted_file, write_json_atomic
from ..storage.sqlite import (
    connect_sqlite,
    default_database_path,
    ensure_sqlite_schema,
    get_storage_metadata,
    set_storage_metadata,
)
from .models import (
    TODO_SCHEMA_VERSION,
    TodoExecutionRecord,
    TodoItem,
    TodoPriority,
    TodoStatus,
    TodoTaskType,
    TodoWorkspaceHint,
)
from .reminder_settings import DEFAULT_DAILY_RESET_HOUR, logical_local_date
from .urgency import build_home_status


def default_todo_store_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "todos.json"


def default_todo_database_path(base_dir: str | Path | None = None) -> Path:
    return default_database_path(base_dir)


class TodoStore:
    """SQLite-backed store for the assistant's real to-do list.

    Legacy JSON paths remain readable for migration and tests, but the default
    runtime path uses SQLite.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        resolved = Path(path) if path is not None else default_todo_database_path()
        self.path = resolved
        self._use_sqlite = resolved.suffix.lower() == ".db" or path is None
        self._legacy_json_path = default_todo_store_path() if self._use_sqlite and path is None else None
        if self._use_sqlite:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)

    def load(self) -> list[TodoItem]:
        if self._use_sqlite:
            return self._load_sqlite()
        return self._load_json()

    def _load_json(self) -> list[TodoItem]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            quarantine_corrupted_file(self.path, source="todo_store", category="todo_store_corrupted", reason="Todo JSON is unreadable.")
            return []
        if not isinstance(payload, dict):
            quarantine_corrupted_file(self.path, source="todo_store", category="todo_store_invalid", reason="Todo JSON root must be an object.")
            return []
        raw_items = payload.get("todos") or []
        if not isinstance(raw_items, list):
            quarantine_corrupted_file(self.path, source="todo_store", category="todo_store_invalid", reason="Todo JSON todos must be a list.")
            return []
        try:
            return [_normalize_item(TodoItem.model_validate(item)) for item in raw_items if isinstance(item, dict)]
        except Exception:
            quarantine_corrupted_file(self.path, source="todo_store", category="todo_store_invalid", reason="Todo items could not be validated.")
            return []

    def save(self, items: Iterable[TodoItem]) -> None:
        if self._use_sqlite:
            self._save_sqlite(items)
            return
        payload = {
            "schema_version": TODO_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "todos": [item.model_dump(mode="json") for item in items],
        }
        write_json_atomic(self.path, payload)

    def list(self, *, include_done: bool = False) -> list[TodoItem]:
        items = self.load()
        if include_done:
            return sorted(items, key=_sort_key)
        return sorted((item for item in items if _is_visible_open_item(item)), key=_sort_key)

    def get(self, item_id: str) -> TodoItem | None:
        if self._use_sqlite:
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)
                self._maybe_import_legacy_json(connection)
                row = connection.execute(
                    "SELECT todo_json FROM todo_items WHERE item_id = ?",
                    (item_id,),
                ).fetchone()
            if row is None:
                return None
            return _normalize_item(TodoItem.model_validate(json.loads(row["todo_json"])))
        for item in self.load():
            if item.id == item_id:
                return item
        return None

    def create(
        self,
        title: str,
        *,
        description: str = "",
        priority: TodoPriority = TodoPriority.NORMAL,
        task_type: TodoTaskType = TodoTaskType.TEMPORARY,
        important: bool = False,
        needs_computer: bool = False,
        due_at: str | None = None,
        reminder_at: str | None = None,
        workspace: TodoWorkspaceHint | None = None,
    ) -> TodoItem:
        item = TodoItem(
            title=title.strip(),
            description=description,
            priority=priority,
            task_type=task_type,
            important=important,
            needs_computer=needs_computer,
            due_at=due_at,
            reminder_at=reminder_at,
            workspace=workspace or TodoWorkspaceHint(),
        )
        if not item.title:
            raise ValueError("Todo title cannot be empty.")
        return self.upsert(item)

    def upsert(self, item: TodoItem) -> TodoItem:
        if self._use_sqlite:
            item.updated_at = datetime.now(UTC).isoformat()
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)
                self._maybe_import_legacy_json(connection)
                self._upsert_sqlite(connection, item)
            return item
        items = self.load()
        item.updated_at = datetime.now(UTC).isoformat()
        by_id = {record.id: record for record in items}
        by_id[item.id] = item
        self.save(by_id.values())
        return item

    def update(self, item_id: str, **changes: object) -> TodoItem | None:
        item = self.get(item_id)
        if item is None:
            return None
        updated = TodoItem.model_validate({**item.model_dump(mode="json"), **changes})
        return self.upsert(updated)

    def mark_done(self, item_id: str, *, daily_completed_on: str | None = None) -> TodoItem | None:
        item = self.get(item_id)
        if item is None:
            return None
        if item.is_daily():
            today = daily_completed_on or logical_local_date(datetime.now(UTC), daily_reset_hour=DEFAULT_DAILY_RESET_HOUR)
            return self.update(
                item_id,
                status=TodoStatus.OPEN,
                completed_at=datetime.now(UTC).isoformat(),
                daily_completed_on=today,
                daily_skipped_on=None,
                snoozed_until=None,
                reminder_repeat_count=0,
            )
        return self.update(
            item_id,
            status=TodoStatus.DONE,
            completed_at=datetime.now(UTC).isoformat(),
        )

    def cancel(self, item_id: str) -> TodoItem | None:
        return self.update(item_id, status=TodoStatus.CANCELLED)

    def update_workspace(
        self,
        item_id: str,
        *,
        workspace: TodoWorkspaceHint,
        needs_computer: bool,
    ) -> TodoItem | None:
        return self.update(
            item_id,
            workspace=workspace,
            needs_computer=needs_computer,
            workspace_confirmed=False,
            workspace_confirmed_at=None,
            trusted_action_keys=[],
        )

    def postpone(self, item_id: str, *, minutes: int) -> TodoItem | None:
        item = self.get(item_id)
        if item is None:
            return None
        now = datetime.now(UTC)
        base = _parse_time(item.snoozed_until or item.reminder_at or item.due_at) or now
        if base < now and (now - base) > timedelta(days=1):
            base = now
        postponed = base + timedelta(minutes=max(1, int(minutes)))
        return self.update(item_id, snoozed_until=postponed.isoformat(), reminder_repeat_count=0)

    def skip_daily_today(
        self,
        item_id: str,
        *,
        skipped_at: str | None = None,
        daily_skipped_on: str | None = None,
    ) -> TodoItem | None:
        item = self.get(item_id)
        if item is None or not item.is_daily():
            return item
        current = _parse_time(skipped_at) or datetime.now(UTC)
        return self.update(
            item_id,
            status=TodoStatus.OPEN,
            daily_skipped_on=daily_skipped_on or logical_local_date(current, daily_reset_hour=DEFAULT_DAILY_RESET_HOUR),
            snoozed_until=None,
            reminder_repeat_count=0,
        )

    def record_execution(
        self,
        item_id: str,
        *,
        trace_id: str,
        status: str,
        message: str = "",
        executed_actions: list[dict[str, str]] | None = None,
    ) -> TodoItem | None:
        return self.update(
            item_id,
            last_execution=TodoExecutionRecord(
                trace_id=trace_id,
                status=status,
                message=message,
                executed_actions=executed_actions or [],
            ),
        )

    def record_reminded(self, item_id: str, *, reminder_key: str, reminded_at: str | None = None) -> TodoItem | None:
        item = self.get(item_id)
        repeat_count = ((item.reminder_repeat_count + 1) if item is not None else 1) if ":repeat:" in reminder_key else 0
        return self.update(
            item_id,
            last_reminder_key=reminder_key,
            last_reminded_at=reminded_at or datetime.now(UTC).isoformat(),
            reminder_repeat_count=repeat_count,
        )

    def mark_workspace_confirmed(
        self,
        item_id: str,
        *,
        trusted_action_keys: list[str] | None = None,
    ) -> TodoItem | None:
        return self.update(
            item_id,
            workspace_confirmed=True,
            workspace_confirmed_at=datetime.now(UTC).isoformat(),
            trusted_action_keys=trusted_action_keys or [],
        )

    def delete(self, item_id: str) -> bool:
        if self._use_sqlite:
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)
                self._maybe_import_legacy_json(connection)
                with connection:
                    result = connection.execute(
                        "DELETE FROM todo_items WHERE item_id = ?",
                        (item_id,),
                    )
            deleted = int(result.rowcount or 0) > 0
            if deleted:
                self._delete_legacy_json_item(item_id)
            return deleted
        items = self.load()
        kept = [item for item in items if item.id != item_id]
        if len(kept) == len(items):
            return False
        self.save(kept)
        return True

    def home_status(self):
        return build_home_status(self.load())

    def _load_sqlite(self) -> list[TodoItem]:
        with connect_sqlite(self.path) as connection:
            ensure_sqlite_schema(connection)
            self._maybe_import_legacy_json(connection)
            rows = connection.execute(
                """
                SELECT todo_json
                FROM todo_items
                ORDER BY priority_rank ASC, COALESCE(next_time, '9999') ASC, created_at ASC
                """
            ).fetchall()
        return [_normalize_item(TodoItem.model_validate(json.loads(row["todo_json"]))) for row in rows]

    def _save_sqlite(self, items: Iterable[TodoItem]) -> None:
        with connect_sqlite(self.path) as connection:
            ensure_sqlite_schema(connection)
            self._maybe_import_legacy_json(connection)
            with connection:
                connection.execute("DELETE FROM todo_items")
                for item in items:
                    self._upsert_sqlite(connection, item)

    def _maybe_import_legacy_json(self, connection: sqlite3.Connection) -> None:
        if self._legacy_json_path is None or not self._legacy_json_path.exists():
            return
        if get_storage_metadata(connection, "todo_legacy_json_imported") == "1":
            return
        row = connection.execute("SELECT COUNT(*) AS count FROM todo_items").fetchone()
        if row is not None and int(row["count"] or 0) > 0:
            set_storage_metadata(connection, "todo_legacy_json_imported", "1")
            return
        legacy_store = TodoStore(self._legacy_json_path)
        items = legacy_store.load()
        with connection:
            for item in items:
                self._upsert_sqlite(connection, item)
            set_storage_metadata(connection, "todo_legacy_json_imported", "1")

    def _delete_legacy_json_item(self, item_id: str) -> None:
        if self._legacy_json_path is None or not self._legacy_json_path.exists():
            return
        legacy_store = TodoStore(self._legacy_json_path)
        legacy_items = legacy_store.load()
        kept = [item for item in legacy_items if item.id != item_id]
        if len(kept) != len(legacy_items):
            legacy_store.save(kept)

    def _upsert_sqlite(self, connection: sqlite3.Connection, item: TodoItem) -> None:
        payload = json.dumps(item.model_dump(mode="json"), ensure_ascii=False)
        connection.execute(
            """
            INSERT INTO todo_items (
                item_id,
                status,
                priority,
                priority_rank,
                important,
                next_time,
                created_at,
                updated_at,
                todo_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                status = excluded.status,
                priority = excluded.priority,
                priority_rank = excluded.priority_rank,
                important = excluded.important,
                next_time = excluded.next_time,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                todo_json = excluded.todo_json
            """,
            (
                item.id,
                item.status.value,
                item.priority.value,
                _priority_rank(item.priority),
                1 if item.important else 0,
                item.next_time(),
                item.created_at,
                item.updated_at,
                payload,
            ),
        )


def _sort_key(item: TodoItem) -> tuple[int, str, str]:
    priority_rank = _priority_rank(item.priority)
    time_value = item.snoozed_until or item.next_time() or "9999"
    return (priority_rank, time_value, item.created_at)


def _is_visible_open_item(item: TodoItem) -> bool:
    return item.status == TodoStatus.OPEN or (item.is_daily() and item.status == TodoStatus.DONE)


def _normalize_item(item: TodoItem) -> TodoItem:
    if item.is_daily() and item.status == TodoStatus.DONE:
        completed_on = _date_from_iso(item.completed_at) or item.daily_completed_on
        return item.model_copy(
            update={
                "status": TodoStatus.OPEN,
                "daily_completed_on": completed_on,
            }
        )
    return item


def _date_from_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.date().isoformat()


def _priority_rank(priority: TodoPriority) -> int:
    return {
        TodoPriority.URGENT: 0,
        TodoPriority.HIGH: 1,
        TodoPriority.NORMAL: 2,
        TodoPriority.LOW: 3,
    }[priority]


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
