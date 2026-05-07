from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

import sys

from desktop_assistant.adapters.windows_app_discovery import (
    ApplicationInventory,
    ApplicationInventoryStore,
    DiscoveredApplication,
)
from desktop_assistant.adapters.windows_window_state import ProcessMatch, WindowMatch
from desktop_assistant.adapters.windows_executor import WindowsExecutor
from desktop_assistant.models import ActionStep, ActionType, ExecutionStatus, RiskLevel
from desktop_assistant.project_locator import ProjectCatalogStore, ProjectLocation


class FakeWindowManager:
    def __init__(
        self,
        *,
        available: bool = True,
        existing: WindowMatch | None = None,
        title_existing: WindowMatch | None = None,
        wait_title_existing: WindowMatch | None = None,
        process_existing: ProcessMatch | None = None,
        visible_windows: list[WindowMatch] | None = None,
    ) -> None:
        self.available = available
        self.existing = existing
        self.title_existing = title_existing
        self.wait_title_existing = wait_title_existing if wait_title_existing is not None else title_existing
        self.process_existing = process_existing
        self.visible_windows = visible_windows or []
        self.process_window_grace_seconds = 0.0
        self.poll_interval_seconds = 0.0
        self.focused: list[WindowMatch] = []
        self.minimized: list[WindowMatch] = []
        self.maximized: list[WindowMatch] = []
        self.restored: list[WindowMatch] = []
        self.closed: list[WindowMatch] = []
        self.waited: list[str] = []
        self.title_keywords: list[list[str]] = []
        self.process_keywords: list[list[str]] = []

    def is_available(self) -> bool:
        return self.available

    def find_by_executable(self, executable_path: str) -> WindowMatch | None:
        return self.existing

    def focus_window(self, match: WindowMatch) -> bool:
        self.focused.append(match)
        return True

    def minimize_window(self, match: WindowMatch) -> bool:
        self.minimized.append(match)
        return True

    def maximize_window(self, match: WindowMatch) -> bool:
        self.maximized.append(match)
        return True

    def restore_window(self, match: WindowMatch) -> bool:
        self.restored.append(match)
        return True

    def close_window(self, match: WindowMatch) -> bool:
        self.closed.append(match)
        return True

    def find_by_hwnd(self, hwnd: int, *, require_visible: bool = True) -> WindowMatch | None:
        for match in [self.existing, self.title_existing, *self.visible_windows]:
            if match is not None and match.hwnd == hwnd:
                return match
        return None

    def get_foreground_window(self) -> WindowMatch | None:
        return self.visible_windows[0] if self.visible_windows else self.existing

    def wait_for_executable(self, executable_path: str, timeout_seconds: float = 5.0) -> WindowMatch | None:
        self.waited.append(executable_path)
        return self.existing

    def find_by_title_keywords(self, keywords) -> WindowMatch | None:
        self.title_keywords.append(list(keywords))
        return self.title_existing

    def wait_for_title_keywords(self, keywords, timeout_seconds: float = 5.0) -> WindowMatch | None:
        self.title_keywords.append(list(keywords))
        return self.wait_title_existing

    def find_process_by_executable(self, executable_path: str) -> ProcessMatch | None:
        return self.process_existing

    def find_process_by_keywords(self, keywords) -> ProcessMatch | None:
        self.process_keywords.append(list(keywords))
        return self.process_existing

    def list_visible_windows(self, limit: int = 50) -> list[WindowMatch]:
        return self.visible_windows[:limit]


class WindowsExecutorTests(unittest.TestCase):
    def _inventory_store(self, apps: list[DiscoveredApplication]) -> tuple[ApplicationInventoryStore, Path]:
        base = Path.cwd() / "runtime" / "test_app_inventory"
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{uuid4().hex}.json"
        store = ApplicationInventoryStore(path=path)
        store.save(ApplicationInventory(generated_at="2026-04-27T00:00:00+00:00", applications=apps))
        return store, path

    def _project_store(self, path_value: Path) -> tuple[ProjectCatalogStore, Path]:
        base = Path.cwd() / "runtime" / "test_project_catalog"
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{uuid4().hex}.json"
        store = ProjectCatalogStore(path)
        store.save([ProjectLocation(name="Test Project", path=str(path_value), kind="project")])
        return store, path

    def test_open_url_accepts_http_urls(self) -> None:
        opened: list[str] = []
        executor = WindowsExecutor(open_url=lambda url: opened.append(url) is None or True)

        result = executor.execute(
            ActionStep(
                action_type=ActionType.OPEN_URL,
                target="https://example.com",
                risk_level=RiskLevel.LOW,
            ),
            step_index=0,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(opened, ["https://example.com"])

    def test_open_url_rejects_non_http_urls(self) -> None:
        executor = WindowsExecutor(open_url=lambda _url: True)

        result = executor.execute(
            ActionStep(
                action_type=ActionType.OPEN_URL,
                target="file:///C:/secret.txt",
                risk_level=RiskLevel.LOW,
            ),
            step_index=0,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "CAPABILITY_VALIDATION_FAILED")
        self.assertEqual(result.diagnosis.details["issues"][0]["code"], "URL_SCHEME_NOT_ALLOWED")

    def test_open_folder_requires_existing_directory(self) -> None:
        opened: list[str] = []
        executor = WindowsExecutor(open_path=opened.append)

        folder = Path.cwd()
        result = executor.execute(
            ActionStep(
                action_type=ActionType.OPEN_FOLDER,
                target=str(folder),
                risk_level=RiskLevel.LOW,
            ),
            step_index=1,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(opened, [str(folder)])

    def test_open_file_requires_existing_file(self) -> None:
        opened: list[str] = []
        executor = WindowsExecutor(open_path=opened.append)

        file_path = Path.cwd() / "pyproject.toml"
        result = executor.execute(
            ActionStep(
                action_type=ActionType.OPEN_FILE,
                target=str(file_path),
                risk_level=RiskLevel.LOW,
            ),
            step_index=2,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(opened, [str(file_path)])

    def test_open_app_uses_inventory_executable(self) -> None:
        opened: list[str] = []
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Python",
                    executable_path=sys.executable,
                    functions=("development",),
                    source="test",
                )
            ]
        )
        executor = WindowsExecutor(open_path=opened.append, app_inventory_store=store)
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Python",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(opened, [sys.executable])

    def test_open_app_prefers_start_menu_shortcut_launch_target(self) -> None:
        opened: list[str] = []
        shortcut_path = Path.cwd() / "runtime" / "test_app_inventory" / f"{uuid4().hex}.lnk"
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        shortcut_path.write_text("shortcut placeholder", encoding="utf-8")
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Battle.net",
                    executable_path=sys.executable,
                    functions=("general_app",),
                    source="start_menu_shortcut",
                    raw_target=str(shortcut_path),
                )
            ]
        )
        executor = WindowsExecutor(open_path=opened.append, app_inventory_store=store)
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Battle.net",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()
            if shortcut_path.exists():
                shortcut_path.unlink()

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(opened, [str(shortcut_path)])

    def test_open_app_focuses_existing_window_without_launching_again(self) -> None:
        opened: list[str] = []
        match = WindowMatch(hwnd=1, title="Python", process_id=123, executable_path=sys.executable)
        window_manager = FakeWindowManager(existing=match)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Python",
                    executable_path=sys.executable,
                    functions=("development",),
                    source="test",
                )
            ]
        )
        executor = WindowsExecutor(
            open_path=opened.append,
            app_inventory_store=store,
            window_manager=window_manager,
        )
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Python",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(opened, [])
        self.assertEqual(window_manager.focused, [match])

    def test_open_app_verifies_launcher_by_window_title_when_executable_changes(self) -> None:
        opened: list[str] = []
        match = WindowMatch(hwnd=10, title="Battle.net", process_id=1234, executable_path="D:/battle_net/Battle.net.exe")
        window_manager = FakeWindowManager(title_existing=None)

        def open_path(path: str) -> None:
            opened.append(path)
            window_manager.title_existing = match

        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="暴雪战网",
                    executable_path=sys.executable,
                    functions=("general_app",),
                    source="test",
                )
            ]
        )
        executor = WindowsExecutor(
            open_path=open_path,
            app_inventory_store=store,
            window_manager=window_manager,
        )
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="战网",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(opened, [sys.executable])
        self.assertEqual(window_manager.focused, [match])
        self.assertIn("by window title", result.message)
        self.assertTrue(any("battle.net" in keywords for keywords in window_manager.title_keywords))
        self.assertTrue(any("战网" in keywords for keywords in window_manager.title_keywords))

    def test_open_app_reports_running_process_without_visible_window(self) -> None:
        opened: list[str] = []
        process = ProcessMatch(process_id=777, executable_path="D:/battle_net/Battle.net.exe")
        window_manager = FakeWindowManager(process_existing=process)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Battle.net",
                    executable_path=sys.executable,
                    functions=("general_app",),
                    source="test",
                )
            ]
        )
        executor = WindowsExecutor(
            open_path=opened.append,
            app_inventory_store=store,
            window_manager=window_manager,
        )
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Battle.net",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "APP_PROCESS_RUNNING_NO_WINDOW")
        self.assertEqual(result.diagnosis.details["process"]["process_id"], 777)
        self.assertEqual(opened, [sys.executable])

    def test_open_app_retries_executable_when_shortcut_only_starts_background_process(self) -> None:
        opened: list[str] = []
        shortcut_path = Path.cwd() / "runtime" / "test_app_inventory" / f"{uuid4().hex}.lnk"
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        shortcut_path.write_text("shortcut placeholder", encoding="utf-8")
        match = WindowMatch(hwnd=10, title="Battle.net", process_id=1234, executable_path="D:/battle_net/Battle.net.exe")
        process = ProcessMatch(process_id=777, executable_path="D:/battle_net/Battle.net Launcher.exe")
        window_manager = FakeWindowManager(process_existing=process)

        def open_path(path: str) -> None:
            opened.append(path)
            if len(opened) == 2:
                window_manager.title_existing = match

        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Battle.net",
                    executable_path=sys.executable,
                    functions=("general_app",),
                    source="start_menu_shortcut",
                    raw_target=str(shortcut_path),
                )
            ]
        )
        executor = WindowsExecutor(
            open_path=open_path,
            app_inventory_store=store,
            window_manager=window_manager,
        )
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Battle.net",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()
            if shortcut_path.exists():
                shortcut_path.unlink()

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(opened, [str(shortcut_path), sys.executable])
        self.assertEqual(window_manager.focused, [match])

    def test_open_app_fails_when_app_is_not_in_inventory(self) -> None:
        store, path = self._inventory_store([])
        executor = WindowsExecutor(app_inventory_store=store)
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Notion",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "APP_NOT_IN_INVENTORY")
        self.assertEqual(result.diagnosis.details["target"], "Notion")

    def test_open_app_blocks_shell_like_apps_even_when_in_inventory(self) -> None:
        opened: list[str] = []
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Safe App",
                    executable_path=str(Path.cwd() / "runtime" / "test_app_inventory" / "powershell.exe"),
                    functions=("system_tool",),
                    source="test",
                )
            ]
        )
        executor = WindowsExecutor(open_path=opened.append, app_inventory_store=store)
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Safe App",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(opened, [])
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "APP_LAUNCH_BLOCKED")

    def test_open_app_reports_missing_executable_path(self) -> None:
        opened: list[str] = []
        missing_exe = Path.cwd() / "runtime" / "test_app_inventory" / f"{uuid4().hex}.exe"
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Missing App",
                    executable_path=str(missing_exe),
                    functions=("test",),
                    source="test",
                )
            ]
        )
        executor = WindowsExecutor(open_path=opened.append, app_inventory_store=store)
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Missing App",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertEqual(opened, [])
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "APP_EXECUTABLE_MISSING")
        self.assertEqual(result.diagnosis.details["executable_path"], str(missing_exe))

    def test_focus_app_requires_existing_window(self) -> None:
        match = WindowMatch(hwnd=2, title="Python", process_id=123, executable_path=sys.executable)
        window_manager = FakeWindowManager(existing=match)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Python",
                    executable_path=sys.executable,
                    functions=("development",),
                    source="test",
                )
            ]
        )
        executor = WindowsExecutor(app_inventory_store=store, window_manager=window_manager)
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.FOCUS_APP,
                    target="Python",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(window_manager.focused, [match])

    def test_focus_app_can_match_window_by_title_for_launcher_apps(self) -> None:
        match = WindowMatch(hwnd=2, title="Battle.net", process_id=123, executable_path="D:/battle_net/Battle.net.exe")
        window_manager = FakeWindowManager(title_existing=match)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Battle.net",
                    executable_path=sys.executable,
                    functions=("general_app",),
                    source="test",
                )
            ]
        )
        executor = WindowsExecutor(app_inventory_store=store, window_manager=window_manager)
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.FOCUS_APP,
                    target="Battle.net",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(window_manager.focused, [match])
        self.assertIn("by window title", result.message)

    def test_list_windows_returns_visible_window_metadata(self) -> None:
        windows = [
            WindowMatch(
                hwnd=1,
                title="QQ",
                process_id=100,
                executable_path="D:/qq/QQ.exe",
                is_minimized=True,
            ),
            WindowMatch(hwnd=2, title="Cursor", process_id=200, executable_path="D:/Cursor/Cursor.exe"),
        ]
        window_manager = FakeWindowManager(visible_windows=windows)
        executor = WindowsExecutor(window_manager=window_manager)

        result = executor.execute(
            ActionStep(
                action_type=ActionType.LIST_WINDOWS,
                target="visible",
                params={"limit": 1},
                risk_level=RiskLevel.LOW,
            ),
            step_index=0,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.metadata["count"], 1)
        self.assertEqual(result.metadata["windows"][0]["title"], "QQ")
        self.assertTrue(result.metadata["windows"][0]["is_minimized"])
        self.assertEqual(result.metadata["foreground_window"]["title"], "QQ")
        self.assertIn("Listed 1 visible window", result.message)

    def test_list_windows_reports_enumeration_failure(self) -> None:
        class DeniedWindowManager(FakeWindowManager):
            def list_visible_windows(self, limit: int = 50) -> list[WindowMatch]:
                raise OSError("access denied")

        executor = WindowsExecutor(window_manager=DeniedWindowManager())

        result = executor.execute(
            ActionStep(
                action_type=ActionType.LIST_WINDOWS,
                target="visible",
                risk_level=RiskLevel.LOW,
            ),
            step_index=0,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "WINDOW_ENUMERATION_FAILED")
        self.assertIn("interactive Windows desktop", result.diagnosis.remedy)

    def test_focus_window_can_match_by_title_without_inventory(self) -> None:
        match = WindowMatch(hwnd=3, title="Project Notes - Obsidian", process_id=300)
        window_manager = FakeWindowManager(title_existing=match)
        executor = WindowsExecutor(window_manager=window_manager)

        result = executor.execute(
            ActionStep(
                action_type=ActionType.FOCUS_WINDOW,
                target="Project Notes",
                risk_level=RiskLevel.LOW,
            ),
            step_index=0,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(window_manager.focused, [match])
        self.assertEqual(result.metadata["window"]["title"], "Project Notes - Obsidian")

    def test_minimize_window_can_match_installed_app(self) -> None:
        match = WindowMatch(hwnd=4, title="Cursor", process_id=400, executable_path=sys.executable)
        window_manager = FakeWindowManager(existing=match)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Cursor",
                    executable_path=sys.executable,
                    functions=("development",),
                    source="test",
                )
            ]
        )
        executor = WindowsExecutor(app_inventory_store=store, window_manager=window_manager)
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.MINIMIZE_WINDOW,
                    target="Cursor",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(window_manager.minimized, [match])

    def test_window_action_returns_post_operation_verification_metadata(self) -> None:
        match = WindowMatch(
            hwnd=4,
            title="Cursor",
            process_id=400,
            executable_path=sys.executable,
            is_minimized=True,
        )
        window_manager = FakeWindowManager(existing=match)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Cursor",
                    executable_path=sys.executable,
                    functions=("development",),
                    source="test",
                )
            ]
        )
        executor = WindowsExecutor(app_inventory_store=store, window_manager=window_manager)
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.MINIMIZE_WINDOW,
                    target="Cursor",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.metadata["verification_status"], "minimized_confirmed")
        self.assertTrue(result.metadata["verified_window"]["is_minimized"])

    def test_close_window_can_match_by_hwnd(self) -> None:
        match = WindowMatch(hwnd=5, title="Untitled - Notepad", process_id=500)
        window_manager = FakeWindowManager(visible_windows=[match])
        executor = WindowsExecutor(window_manager=window_manager)

        result = executor.execute(
            ActionStep(
                action_type=ActionType.CLOSE_WINDOW,
                target="hwnd:5",
                risk_level=RiskLevel.MEDIUM,
            ),
            step_index=0,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(window_manager.closed, [match])

    def test_window_action_reports_missing_target_with_keywords(self) -> None:
        window_manager = FakeWindowManager()
        executor = WindowsExecutor(window_manager=window_manager)

        result = executor.execute(
            ActionStep(
                action_type=ActionType.MAXIMIZE_WINDOW,
                target="DefinitelyAbsentZzz",
                risk_level=RiskLevel.LOW,
            ),
            step_index=0,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "WINDOW_NOT_FOUND")
        self.assertIn("definitelyabsentzzz", result.diagnosis.details["title_keywords"])

    def test_window_action_reports_lookup_failure(self) -> None:
        class DeniedWindowManager(FakeWindowManager):
            def find_by_title_keywords(self, keywords) -> WindowMatch | None:
                raise OSError("access denied")

        executor = WindowsExecutor(window_manager=DeniedWindowManager())

        result = executor.execute(
            ActionStep(
                action_type=ActionType.RESTORE_WINDOW,
                target="Some Window",
                risk_level=RiskLevel.LOW,
            ),
            step_index=0,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "WINDOW_LOOKUP_FAILED")
        self.assertEqual(result.diagnosis.details["operation"], "restore")

    def test_open_project_uses_project_catalog(self) -> None:
        opened: list[str] = []
        store, path = self._project_store(Path.cwd())
        executor = WindowsExecutor(open_path=opened.append, project_catalog_store=store)
        try:
            result = executor.execute(
                ActionStep(
                    action_type=ActionType.OPEN_PROJECT,
                    target="Test Project",
                    risk_level=RiskLevel.LOW,
                ),
                step_index=0,
                trace_id="trace",
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(opened, [str(Path.cwd())])

    def test_focus_timer_is_simulated(self) -> None:
        executor = WindowsExecutor()

        result = executor.execute(
            ActionStep(
                action_type=ActionType.START_FOCUS_TIMER,
                target="25m",
                risk_level=RiskLevel.LOW,
            ),
            step_index=0,
            trace_id="trace",
        )

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
