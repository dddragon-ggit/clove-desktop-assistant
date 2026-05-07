from __future__ import annotations

import unittest
from pathlib import Path
from shutil import rmtree
from unittest.mock import patch
from uuid import uuid4

from desktop_assistant.storage import quarantine_corrupted_file, write_json_atomic, write_text_atomic
from desktop_assistant.storage.recovery_events import RecoveryEventStore


def _workspace_path() -> Path:
    base = Path.cwd() / "runtime" / "test_json_atomic"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


class AtomicJsonWriteTests(unittest.TestCase):
    def test_write_text_atomic_replaces_file_contents(self) -> None:
        root = _workspace_path()
        try:
            path = root / "sample.json"
            path.write_text("old", encoding="utf-8")

            write_text_atomic(path, "new")

            self.assertEqual(path.read_text(encoding="utf-8"), "new")
        finally:
            rmtree(root, ignore_errors=True)

    def test_write_json_atomic_keeps_original_file_when_replace_fails(self) -> None:
        root = _workspace_path()
        try:
            path = root / "sample.json"
            path.write_text('{"value": "old"}', encoding="utf-8")

            with patch("desktop_assistant.storage.json_files.os.replace", side_effect=OSError("disk busy")):
                with self.assertRaises(OSError):
                    write_json_atomic(path, {"value": "new"})

            self.assertEqual(path.read_text(encoding="utf-8"), '{"value": "old"}')
            leftovers = [item.name for item in root.iterdir() if item.name != "sample.json"]
            self.assertEqual(leftovers, [])
        finally:
            rmtree(root, ignore_errors=True)

    def test_quarantine_corrupted_file_renames_original(self) -> None:
        root = _workspace_path()
        try:
            path = root / "sample.json"
            path.write_text("broken", encoding="utf-8")

            quarantined = quarantine_corrupted_file(
                path,
                source="todo_store",
                category="todo_store_corrupted",
                reason="Todo JSON is unreadable.",
            )

            self.assertFalse(path.exists())
            self.assertIsNotNone(quarantined)
            self.assertTrue(quarantined.exists())
            self.assertEqual(quarantined.read_text(encoding="utf-8"), "broken")
        finally:
            rmtree(root, ignore_errors=True)

    def test_quarantine_records_recovery_event(self) -> None:
        root = _workspace_path()
        try:
            path = root / "sample.json"
            recovery_path = root / "recovery_events.json"
            path.write_text("broken", encoding="utf-8")

            with patch(
                "desktop_assistant.storage.recovery_events.default_recovery_event_path",
                return_value=recovery_path,
            ):
                quarantined = quarantine_corrupted_file(
                    path,
                    source="todo_store",
                    category="todo_store_corrupted",
                    reason="Todo JSON is unreadable.",
                )

            latest = RecoveryEventStore(recovery_path).latest(max_age_hours=9999)
            self.assertIsNotNone(quarantined)
            self.assertIsNotNone(latest)
            self.assertEqual(latest.source, "todo_store")
            self.assertEqual(latest.category, "todo_store_corrupted")
            self.assertEqual(latest.path, str(path))
            self.assertEqual(latest.quarantined_path, str(quarantined))
        finally:
            rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
