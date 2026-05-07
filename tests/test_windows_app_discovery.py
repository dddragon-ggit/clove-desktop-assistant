from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from desktop_assistant.adapters.windows_app_discovery import (
    ApplicationInventoryStore,
    DiscoveredApplication,
    build_app_name_index,
    find_application,
    _extract_executable_path,
    _infer_application_functions,
    _is_uninstall_or_setup_name,
    _is_unsafe_executable_path,
)
from desktop_assistant.storage.recovery_events import RecoveryEventStore


class FakeDiscovery:
    def __init__(self) -> None:
        self.calls = 0

    def discover(self, *, include_start_menu: bool = True, limit: int | None = None) -> list[DiscoveredApplication]:
        self.calls += 1
        return [
            DiscoveredApplication(
                name="Cursor",
                executable_path="C:\\Users\\me\\AppData\\Local\\Programs\\Cursor\\Cursor.exe",
                functions=("development",),
                source="test",
            )
        ]


class WindowsApplicationDiscoveryTests(unittest.TestCase):
    def _inventory_path(self) -> Path:
        base = Path.cwd() / "runtime" / "test_app_inventory"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{uuid4().hex}.json"

    def test_extract_executable_path_from_quoted_command(self) -> None:
        self.assertEqual(
            _extract_executable_path('"C:\\Program Files\\App\\app.exe" --flag'),
            "C:\\Program Files\\App\\app.exe",
        )

    def test_infer_application_functions(self) -> None:
        self.assertIn("development", _infer_application_functions("Cursor", "C:\\Tools\\Cursor.exe"))
        self.assertIn("web_browser", _infer_application_functions("Google Chrome", None))

    def test_rejects_uninstaller_executable_as_launch_target(self) -> None:
        self.assertTrue(_is_unsafe_executable_path("C:\\Apps\\Example\\Uninstall-Example.exe"))
        self.assertTrue(_is_unsafe_executable_path("C:\\Apps\\Example\\Cleanup.exe"))
        self.assertFalse(_is_unsafe_executable_path("C:\\Apps\\Example\\Example.exe"))

    def test_rejects_uninstall_shortcut_names(self) -> None:
        self.assertTrue(_is_uninstall_or_setup_name("卸载微信"))
        self.assertTrue(_is_uninstall_or_setup_name("Example Setup"))
        self.assertFalse(_is_uninstall_or_setup_name("微信"))

    def test_find_application_matches_alias_in_name_or_path(self) -> None:
        apps = [
            DiscoveredApplication(
                name="暴雪战网",
                executable_path="D:\\battle_net\\Battle.net\\Battle.net.exe",
                functions=("general_app",),
                source="test",
            ),
            DiscoveredApplication(
                name="战网卸载",
                executable_path="D:\\battle_net\\Battle.net\\Uninstall.exe",
                functions=("general_app",),
                source="test",
            ),
        ]

        app = find_application(apps, "Battle.net（战网）")

        self.assertIsNotNone(app)
        self.assertEqual(app.name, "暴雪战网")

    def test_find_application_matches_embedded_chinese_app_name(self) -> None:
        apps = [
            DiscoveredApplication(
                name="暴雪战网",
                executable_path="D:\\battle_net\\Battle.net\\Battle.net Launcher.exe",
                functions=("general_app",),
                source="test",
            )
        ]

        app = find_application(apps, "打开战网应用")

        self.assertIsNotNone(app)
        self.assertEqual(app.name, "暴雪战网")

    def test_inventory_store_writes_once_then_loads_cache(self) -> None:
        path = self._inventory_path()
        discovery = FakeDiscovery()
        store = ApplicationInventoryStore(path=path)
        try:
            first = store.ensure(discovery=discovery)
            second = store.ensure(discovery=discovery)
            index_names = store.load_name_index().names
        finally:
            if path.exists():
                path.unlink()
            if store.name_index_path.exists():
                store.name_index_path.unlink()

        self.assertEqual(discovery.calls, 1)
        self.assertEqual(first.applications[0].name, "Cursor")
        self.assertEqual(second.applications[0].executable_path, "C:\\Users\\me\\AppData\\Local\\Programs\\Cursor\\Cursor.exe")
        self.assertEqual(index_names, ["Cursor"])

    def test_inventory_store_refreshes_corrupt_cache(self) -> None:
        path = self._inventory_path()
        path.write_text("{not json", encoding="utf-8")
        discovery = FakeDiscovery()
        store = ApplicationInventoryStore(path=path)
        try:
            inventory = store.ensure(discovery=discovery)
        finally:
            if path.exists():
                path.unlink()
            if store.name_index_path.exists():
                store.name_index_path.unlink()

        self.assertEqual(discovery.calls, 1)
        self.assertEqual(inventory.applications[0].name, "Cursor")

    def test_build_app_name_index_contains_only_unique_names(self) -> None:
        path = self._inventory_path()
        store = ApplicationInventoryStore(path=path)
        try:
            inventory = store.ensure(discovery=FakeDiscovery())
            index = build_app_name_index(inventory)
        finally:
            if path.exists():
                path.unlink()
            if store.name_index_path.exists():
                store.name_index_path.unlink()

        self.assertEqual(index.names, ["Cursor"])

    def test_load_quarantines_invalid_inventory_and_records_recovery(self) -> None:
        path = self._inventory_path()
        recovery_path = path.parent / f"{path.stem}_recovery.json"
        path.write_text("{not json", encoding="utf-8")
        store = ApplicationInventoryStore(path=path)
        try:
            from unittest.mock import patch

            with patch(
                "desktop_assistant.storage.recovery_events.default_recovery_event_path",
                return_value=recovery_path,
            ):
                with self.assertRaises(ValueError):
                    store.load()
            latest = RecoveryEventStore(recovery_path).latest(max_age_hours=9999)
        finally:
            for item in path.parent.glob(f"{path.name}.corrupt*"):
                item.unlink(missing_ok=True)
            if path.exists():
                path.unlink()
            if store.name_index_path.exists():
                store.name_index_path.unlink()
            if recovery_path.exists():
                recovery_path.unlink()

        self.assertIsNotNone(latest)
        self.assertEqual(latest.source, "app_inventory_store")


if __name__ == "__main__":
    unittest.main()
