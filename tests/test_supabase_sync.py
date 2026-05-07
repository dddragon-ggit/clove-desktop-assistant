from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from desktop_assistant.sync.config import SupabaseConfig, SupabaseConfigStore
from desktop_assistant.sync.supabase_sync import (
    SupabaseSyncService,
    row_to_todo,
    todo_to_row,
)
from desktop_assistant.todo.models import (
    TodoItem,
    TodoPriority,
    TodoStatus,
    TodoTaskType,
)


def _make_item(**overrides) -> TodoItem:
    defaults = {
        "title": "Test task",
        "status": TodoStatus.OPEN,
        "priority": TodoPriority.NORMAL,
        "task_type": TodoTaskType.TEMPORARY,
    }
    defaults.update(overrides)
    return TodoItem(**defaults)


class FakeSupabaseTable:
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.last_query: list[dict] | None = None

    def upsert(self, rows):
        if isinstance(rows, dict):
            rows = [rows]
        for row in rows:
            self.rows[row["id"]] = row
        return self

    def select(self, *_args):
        self.last_query = list(self.rows.values())
        return self

    def delete(self):
        return self

    def eq(self, _col, val):
        if val in self.rows:
            del self.rows[val]
        return self

    def execute(self):
        class Result:
            def __init__(self, data):
                self.data = data
        if self.last_query is not None:
            data = self.last_query
            self.last_query = None
            return Result(data)
        return Result([])


class FakeSupabaseClient:
    def __init__(self):
        self.table_store: dict[str, FakeSupabaseTable] = {}

    def table(self, name: str) -> FakeSupabaseTable:
        if name not in self.table_store:
            self.table_store[name] = FakeSupabaseTable()
        return self.table_store[name]


class TestTodoRowConversion(unittest.TestCase):
    def test_todo_to_row_basic(self):
        item = _make_item(title="Buy milk")
        row = todo_to_row(item, "device-abc")
        self.assertEqual(row["title"], "Buy milk")
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["priority"], "normal")
        self.assertEqual(row["task_type"], "temporary")
        self.assertEqual(row["device_id"], "device-abc")
        self.assertFalse(row["important"])

    def test_roundtrip(self):
        item = _make_item(
            title="Roundtrip",
            priority=TodoPriority.HIGH,
            task_type=TodoTaskType.DAILY,
            important=True,
            needs_computer=True,
            due_at="2026-05-10T09:00:00+00:00",
        )
        row = todo_to_row(item, "dev1")
        restored = row_to_todo(row)
        self.assertEqual(restored.id, item.id)
        self.assertEqual(restored.title, "Roundtrip")
        self.assertEqual(restored.priority, TodoPriority.HIGH)
        self.assertEqual(restored.task_type, TodoTaskType.DAILY)
        self.assertTrue(restored.important)
        self.assertTrue(restored.needs_computer)
        self.assertEqual(restored.due_at, "2026-05-10T09:00:00+00:00")

    def test_row_to_todo_defaults(self):
        row = {"id": "x", "title": "Minimal"}
        item = row_to_todo(row)
        self.assertEqual(item.title, "Minimal")
        self.assertEqual(item.status, TodoStatus.OPEN)
        self.assertEqual(item.priority, TodoPriority.NORMAL)


class TestSupabaseSyncService(unittest.TestCase):
    def _make_service(self):
        client = FakeSupabaseClient()
        with tempfile.TemporaryDirectory() as td:
            svc = SupabaseSyncService(client, device_id_path=Path(td))
            yield svc, client, td

    def test_device_id_stable(self):
        client = FakeSupabaseClient()
        with tempfile.TemporaryDirectory() as td:
            svc1 = SupabaseSyncService(client, device_id_path=Path(td))
            id1 = svc1.device_id
            svc2 = SupabaseSyncService(client, device_id_path=Path(td))
            id2 = svc2.device_id
            self.assertEqual(id1, id2)
            self.assertTrue(id1.startswith("device-"))

    def test_push_item(self):
        client = FakeSupabaseClient()
        with tempfile.TemporaryDirectory() as td:
            svc = SupabaseSyncService(client, device_id_path=Path(td))
            item = _make_item(title="Push test")
            svc.push_item(item)
            rows = client.table("todos").rows
            self.assertIn(item.id, rows)
            self.assertEqual(rows[item.id]["title"], "Push test")

    def test_delete_item(self):
        client = FakeSupabaseClient()
        with tempfile.TemporaryDirectory() as td:
            svc = SupabaseSyncService(client, device_id_path=Path(td))
            item = _make_item(title="To delete")
            svc.push_item(item)
            self.assertIn(item.id, client.table("todos").rows)
            svc.delete_item(item.id)
            self.assertNotIn(item.id, client.table("todos").rows)

    def test_pull_all(self):
        client = FakeSupabaseClient()
        with tempfile.TemporaryDirectory() as td:
            svc = SupabaseSyncService(client, device_id_path=Path(td))
            item = _make_item(title="Pulled")
            svc.push_item(item)
            items = svc.pull_all()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].title, "Pulled")

    def test_full_sync_merge(self):
        client = FakeSupabaseClient()
        with tempfile.TemporaryDirectory() as td:
            svc = SupabaseSyncService(client, device_id_path=Path(td))
            local = _make_item(title="Local only")
            local.updated_at = "2026-05-07T10:00:00+00:00"
            svc.push_item(_make_item(title="Remote only"))
            merged, stats = svc.full_sync([local])
            titles = {i.title for i in merged}
            self.assertIn("Local only", titles)
            self.assertIn("Remote only", titles)
            self.assertEqual(stats["merged_count"], 2)

    def test_full_sync_local_wins_on_tie(self):
        client = FakeSupabaseClient()
        with tempfile.TemporaryDirectory() as td:
            svc = SupabaseSyncService(client, device_id_path=Path(td))
            local = _make_item(title="Local version")
            local.updated_at = "2026-05-07T10:00:00+00:00"
            remote = _make_item(id=local.id, title="Remote version")
            remote.updated_at = "2026-05-07T10:00:00+00:00"
            svc.push_item(remote)
            merged, _ = svc.full_sync([local])
            match = [i for i in merged if i.id == local.id]
            self.assertEqual(match[0].title, "Local version")

    def test_full_sync_remote_wins_when_newer(self):
        client = FakeSupabaseClient()
        with tempfile.TemporaryDirectory() as td:
            svc = SupabaseSyncService(client, device_id_path=Path(td))
            local = _make_item(title="Old local")
            local.updated_at = "2026-05-07T08:00:00+00:00"
            remote = _make_item(id=local.id, title="New remote")
            remote.updated_at = "2026-05-07T12:00:00+00:00"
            svc.push_item(remote)
            merged, _ = svc.full_sync([local])
            match = [i for i in merged if i.id == local.id]
            self.assertEqual(match[0].title, "New remote")

    def test_is_remote_change(self):
        client = FakeSupabaseClient()
        with tempfile.TemporaryDirectory() as td:
            svc = SupabaseSyncService(client, device_id_path=Path(td))
            self.assertTrue(svc.is_remote_change({"device_id": "other"}))
            self.assertFalse(svc.is_remote_change({"device_id": svc.device_id}))


class TestSupabaseConfigStore(unittest.TestCase):
    def test_load_default(self):
        with tempfile.TemporaryDirectory() as td:
            store = SupabaseConfigStore(Path(td) / "config.json")
            config = store.load()
            self.assertFalse(config.enabled)
            self.assertEqual(config.url, "")

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            store = SupabaseConfigStore(Path(td) / "config.json")
            config = SupabaseConfig(url="https://test.supabase.co", key="sb_test", enabled=True)
            store.save(config)
            loaded = store.load()
            self.assertTrue(loaded.enabled)
            self.assertEqual(loaded.url, "https://test.supabase.co")

    def test_describe_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            store = SupabaseConfigStore(Path(td) / "config.json")
            self.assertIn("disabled", store.describe())

    def test_describe_enabled_masks_key(self):
        with tempfile.TemporaryDirectory() as td:
            store = SupabaseConfigStore(Path(td) / "config.json")
            config = SupabaseConfig(url="https://x.supabase.co", key="sb_publishable_abcdef1234567890", enabled=True)
            store.save(config)
            desc = store.describe()
            self.assertIn("enabled", desc)
            self.assertIn("sb_publish", desc)
            self.assertNotIn("abcdef1234567890", desc)


if __name__ == "__main__":
    unittest.main()
