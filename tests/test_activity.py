from __future__ import annotations

import unittest
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from desktop_assistant.activity import (
    ActivityFile,
    ActivityResolver,
    ActivitySnapshot,
    ActivityStore,
    DesktopActivitySampler,
    StaticRecentFileProvider,
)
from desktop_assistant.adapters.windows_app_models import ApplicationInventory, DiscoveredApplication
from desktop_assistant.adapters.windows_window_state import WindowMatch
from desktop_assistant.projects.models import ProjectLocation


def _workspace_path() -> Path:
    base = Path.cwd() / "runtime" / "test_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"activity_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


class _FakeWindowManager:
    def __init__(self, window: WindowMatch | None) -> None:
        self.window = window

    def is_available(self) -> bool:
        return True

    def get_foreground_window(self) -> WindowMatch | None:
        return self.window


class _FakeProcessMetadataProvider:
    def __init__(self, command_line: str) -> None:
        self.command_line = command_line

    def get_command_line(self, process_id: int) -> str:
        return self.command_line


class _FakeInventoryStore:
    def __init__(self, inventory: ApplicationInventory) -> None:
        self.inventory = inventory

    def ensure(self, *, refresh: bool = False) -> ApplicationInventory:
        return self.inventory


class _FakeProjectStore:
    def __init__(self, projects: list[ProjectLocation]) -> None:
        self.projects = projects

    def ensure(self) -> list[ProjectLocation]:
        return self.projects


class ActivityResolverTests(unittest.TestCase):
    def test_command_line_file_is_resolved_without_treating_exe_as_document(self) -> None:
        root = _workspace_path()
        try:
            app_path = root / "Cursor.exe"
            project_path = root / "desktop_assistant"
            project_path.mkdir()
            file_path = project_path / "notes.md"
            file_path.write_text("# Notes", encoding="utf-8")

            inventory = ApplicationInventory(
                generated_at="now",
                applications=[
                    DiscoveredApplication(
                        name="Cursor",
                        executable_path=str(app_path),
                        functions=("coding",),
                        source="test",
                    )
                ],
            )
            resolver = ActivityResolver(
                inventory=inventory,
                projects=[ProjectLocation("desktop_assistant", str(project_path), "project")],
            )
            window = WindowMatch(
                hwnd=100,
                title="notes.md - desktop_assistant - Cursor",
                process_id=200,
                executable_path=str(app_path),
            )

            snapshot = resolver.resolve(
                window=window,
                command_line=f'"{app_path}" "{file_path}"',
            )

            self.assertEqual(snapshot.active_app.name, "Cursor")
            self.assertEqual(snapshot.active_file.path, str(file_path))
            self.assertEqual(snapshot.active_file.source, "process_command_line")
            self.assertEqual(snapshot.active_project.name, "desktop_assistant")
        finally:
            rmtree(root, ignore_errors=True)

    def test_window_title_can_match_recent_file_and_project(self) -> None:
        root = _workspace_path()
        try:
            project_path = root / "reports"
            project_path.mkdir()
            file_path = project_path / "weekly-report.docx"
            recent_file = ActivityFile(
                name="weekly-report.docx",
                path=str(file_path),
                source="windows_recent",
                confidence="medium",
            )
            resolver = ActivityResolver(
                projects=[ProjectLocation("reports", str(project_path), "project")],
            )
            window = WindowMatch(
                hwnd=101,
                title="weekly-report.docx - Word",
                process_id=201,
                executable_path=r"C:\Program Files\Microsoft Office\WINWORD.EXE",
            )

            snapshot = resolver.resolve(window=window, recent_files=[recent_file])

            self.assertEqual(snapshot.active_file.path, str(file_path))
            self.assertEqual(snapshot.active_file.source, "window_title_recent_file")
            self.assertEqual(snapshot.active_project.name, "reports")
            self.assertEqual(snapshot.active_app.name, "WINWORD")
        finally:
            rmtree(root, ignore_errors=True)

    def test_window_title_file_name_fallback_does_not_claim_path(self) -> None:
        resolver = ActivityResolver()
        window = WindowMatch(
            hwnd=102,
            title="draft.py - Python",
            process_id=202,
            executable_path="",
        )

        snapshot = resolver.resolve(window=window)

        self.assertEqual(snapshot.active_file.name, "draft.py")
        self.assertEqual(snapshot.active_file.path, "")
        self.assertEqual(snapshot.active_file.confidence, "low")


class ActivityStoreTests(unittest.TestCase):
    def test_append_deduplicates_adjacent_same_activity_and_respects_recent_limit(self) -> None:
        root = _workspace_path()
        try:
            store = ActivityStore(root / "activity.json")
            first = ActivitySnapshot(active_file=ActivityFile(name="a.md", path=r"D:\a.md"))
            second = ActivitySnapshot(active_file=ActivityFile(name="a.md", path=r"D:\a.md"))

            store.append(first)
            store.append(second)

            self.assertEqual(len(store.load()), 1)
            self.assertEqual(store.recent(0), [])
            self.assertEqual(len(store.recent(1)), 1)
        finally:
            rmtree(root, ignore_errors=True)


class DesktopActivitySamplerTests(unittest.TestCase):
    def test_sampler_combines_window_process_inventory_projects_and_recent_files(self) -> None:
        root = _workspace_path()
        try:
            app_path = root / "Cursor.exe"
            project_path = root / "sample_project"
            project_path.mkdir()
            file_path = project_path / "main.py"
            file_path.write_text("print('ok')", encoding="utf-8")
            inventory = ApplicationInventory(
                generated_at="now",
                applications=[
                    DiscoveredApplication(
                        name="Cursor",
                        executable_path=str(app_path),
                        functions=("coding",),
                        source="test",
                    )
                ],
            )
            window = WindowMatch(
                hwnd=103,
                title="main.py - sample_project - Cursor",
                process_id=203,
                executable_path=str(app_path),
            )
            store = ActivityStore(root / "activity.json")
            sampler = DesktopActivitySampler(
                window_manager=_FakeWindowManager(window),
                app_inventory_store=_FakeInventoryStore(inventory),
                project_catalog_store=_FakeProjectStore(
                    [ProjectLocation("sample_project", str(project_path), "project")]
                ),
                process_metadata_provider=_FakeProcessMetadataProvider(f'"{app_path}" "{file_path}"'),
                recent_file_provider=StaticRecentFileProvider([]),
                activity_store=store,
            )

            snapshot = sampler.sample_and_store()

            self.assertEqual(snapshot.active_app.name, "Cursor")
            self.assertEqual(snapshot.active_file.path, str(file_path))
            self.assertEqual(snapshot.active_project.name, "sample_project")
            self.assertEqual(len(store.load()), 1)
        finally:
            rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
