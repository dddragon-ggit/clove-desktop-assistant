from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..todo.models import (
    TodoItem,
    TodoPriority,
    TodoStatus,
    TodoTaskType,
    TodoWorkspaceHint,
)

logger = logging.getLogger(__name__)

_SUPABASE_SYNC_COLUMNS = {
    "id", "title", "description", "status", "priority", "task_type",
    "important", "needs_computer", "due_at", "reminder_at", "snoozed_until",
    "daily_completed_on", "daily_skipped_on", "created_at", "updated_at",
    "completed_at", "device_id",
}


def _default_device_id_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "device_id.txt"


def _load_or_create_device_id(path: Path) -> str:
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    new_id = f"device-{uuid4().hex[:12]}"
    path.write_text(new_id, encoding="utf-8")
    return new_id


def todo_to_row(item: TodoItem, device_id: str) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "status": item.status.value,
        "priority": item.priority.value,
        "task_type": item.task_type.value,
        "important": item.important,
        "needs_computer": item.needs_computer,
        "due_at": item.due_at,
        "reminder_at": item.reminder_at,
        "snoozed_until": item.snoozed_until,
        "daily_completed_on": item.daily_completed_on,
        "daily_skipped_on": item.daily_skipped_on,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "completed_at": item.completed_at,
        "device_id": device_id,
    }


def row_to_todo(row: dict) -> TodoItem:
    return TodoItem(
        id=row["id"],
        title=row["title"],
        description=row.get("description") or "",
        status=TodoStatus(row.get("status") or "open"),
        priority=TodoPriority(row.get("priority") or "normal"),
        task_type=TodoTaskType(row.get("task_type") or "temporary"),
        important=bool(row.get("important")),
        needs_computer=bool(row.get("needs_computer")),
        due_at=row.get("due_at"),
        reminder_at=row.get("reminder_at"),
        snoozed_until=row.get("snoozed_until"),
        daily_completed_on=row.get("daily_completed_on"),
        daily_skipped_on=row.get("daily_skipped_on"),
        created_at=row.get("created_at") or datetime.now(UTC).isoformat(),
        updated_at=row.get("updated_at") or datetime.now(UTC).isoformat(),
        completed_at=row.get("completed_at"),
    )


def _parse_ts(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


class SupabaseSyncService:
    def __init__(
        self,
        client,
        *,
        device_id_path: str | Path | None = None,
    ) -> None:
        self._client = client
        self._device_id = _load_or_create_device_id(
            _default_device_id_path(device_id_path),
        )

    @property
    def device_id(self) -> str:
        return self._device_id

    def push_item(self, item: TodoItem) -> None:
        row = todo_to_row(item, self._device_id)
        self._client.table("todos").upsert(row).execute()
        logger.debug("Pushed todo %s to Supabase", item.id)

    def delete_item(self, item_id: str) -> None:
        self._client.table("todos").delete().eq("id", item_id).execute()
        logger.debug("Deleted todo %s from Supabase", item_id)

    def pull_all(self) -> list[TodoItem]:
        result = self._client.table("todos").select("*").execute()
        return [row_to_todo(row) for row in result.data]

    def push_all(self, items: list[TodoItem]) -> int:
        if not items:
            return 0
        rows = [todo_to_row(item, self._device_id) for item in items]
        self._client.table("todos").upsert(rows).execute()
        logger.debug("Pushed %d todos to Supabase", len(rows))
        return len(rows)

    def full_sync(self, local_items: list[TodoItem]) -> tuple[list[TodoItem], dict]:
        remote_rows = self._client.table("todos").select("*").execute().data
        remote_map: dict[str, dict] = {r["id"]: r for r in remote_rows}
        local_map: dict[str, TodoItem] = {item.id: item for item in local_items}

        merged: dict[str, TodoItem] = {}
        upsert_rows: list[dict] = []

        for item_id, local in local_map.items():
            remote = remote_map.get(item_id)
            if remote is None:
                merged[item_id] = local
                upsert_rows.append(todo_to_row(local, self._device_id))
            else:
                remote_ts = _parse_ts(remote.get("updated_at"))
                local_ts = _parse_ts(local.updated_at)
                if local_ts >= remote_ts:
                    merged[item_id] = local
                    upsert_rows.append(todo_to_row(local, self._device_id))
                else:
                    merged[item_id] = row_to_todo(remote)

        for item_id, remote in remote_map.items():
            if item_id not in local_map:
                merged[item_id] = row_to_todo(remote)

        if upsert_rows:
            self._client.table("todos").upsert(upsert_rows).execute()

        stats = {
            "local_count": len(local_items),
            "remote_count": len(remote_rows),
            "merged_count": len(merged),
            "pushed_count": len(upsert_rows),
        }
        logger.debug("Full sync stats: %s", stats)
        return sorted(merged.values(), key=lambda i: i.created_at), stats

    def is_remote_change(self, row: dict) -> bool:
        return row.get("device_id") != self._device_id
