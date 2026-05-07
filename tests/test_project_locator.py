from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from desktop_assistant.project_locator import (
    ProjectCatalogStore,
    ProjectLocation,
    discover_project_locations,
    find_project_location,
)


class ProjectLocatorTests(unittest.TestCase):
    def _path(self) -> Path:
        base = Path.cwd() / "runtime" / "test_projects"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{uuid4().hex}.json"

    def test_find_project_location_matches_known_folder_alias(self) -> None:
        location = find_project_location(
            [
                ProjectLocation(
                    name="current workspace",
                    path=str(Path.cwd()),
                    kind="project",
                )
            ],
            "当前项目",
        )

        self.assertIsNotNone(location)
        self.assertEqual(location.name, "current workspace")

    def test_store_merges_defaults_and_user_projects(self) -> None:
        path = self._path()
        store = ProjectCatalogStore(path)
        try:
            store.save([ProjectLocation(name="Cursor Work", path=str(Path.cwd()), kind="project")])
            locations = store.ensure()
            loaded = ProjectCatalogStore(path).find("Cursor Work")
        finally:
            if path.exists():
                path.unlink()

        self.assertTrue(any(location.name == "current workspace" for location in locations))
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.path, str(Path.cwd()))

    def test_upsert_updates_project_by_name(self) -> None:
        path = self._path()
        store = ProjectCatalogStore(path)
        try:
            store.upsert(ProjectLocation(name="Cursor Work", path="D:/old", kind="project"))
            store.upsert(ProjectLocation(name="Cursor Work", path=str(Path.cwd()), kind="folder"))
            loaded = store.find("Cursor Work")
        finally:
            if path.exists():
                path.unlink()

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.path, str(Path.cwd()))
        self.assertEqual(loaded.kind, "folder")

    def test_delete_removes_project_entry(self) -> None:
        path = self._path()
        store = ProjectCatalogStore(path)
        try:
            store.upsert(ProjectLocation(name="Needle Project", path=str(Path.cwd()), kind="project"))
            deleted = store.delete("Needle Project")
            names = {location.name for location in ProjectCatalogStore(path).load()}
            loaded = ProjectCatalogStore(path).find("Needle Project")
        finally:
            if path.exists():
                path.unlink()

        self.assertTrue(deleted)
        self.assertNotIn("Needle Project", names)
        self.assertIsNone(loaded)

    def test_discover_project_locations_finds_project_markers(self) -> None:
        base = Path.cwd() / "runtime" / "test_projects"
        base.mkdir(parents=True, exist_ok=True)
        root = base / uuid4().hex
        try:
            project = root / "NeedleProject"
            project.mkdir(parents=True)
            (project / "pyproject.toml").write_text("[project]\nname='needle'\n", encoding="utf-8")
            discovered = discover_project_locations(roots=[root], max_depth=2)
        finally:
            if root.exists():
                shutil.rmtree(root)

        self.assertTrue(any(location.name == "NeedleProject" for location in discovered))
        needle = next(location for location in discovered if location.name == "NeedleProject")
        self.assertEqual(needle.kind, "project")
        self.assertIn("pyproject.toml", needle.description)

    def test_refresh_discovered_merges_projects_into_catalog(self) -> None:
        base = Path.cwd() / "runtime" / "test_projects"
        base.mkdir(parents=True, exist_ok=True)
        path = self._path()
        root = base / uuid4().hex
        try:
            project = root / "WorkspaceApp"
            project.mkdir(parents=True)
            (project / "package.json").write_text("{}", encoding="utf-8")
            store = ProjectCatalogStore(path)
            locations = store.refresh_discovered(roots=[root], max_depth=2)
            loaded = store.find("WorkspaceApp")
        finally:
            if path.exists():
                path.unlink()
            if root.exists():
                shutil.rmtree(root)

        self.assertTrue(any(location.name == "WorkspaceApp" for location in locations))
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "WorkspaceApp")

    def test_project_store_quarantines_corrupted_catalog_and_recovers(self) -> None:
        path = self._path()
        path.write_text("{not-json", encoding="utf-8")
        try:
            loaded = ProjectCatalogStore(path).load()
        finally:
            quarantined = list(path.parent.glob(f"{path.name}.corrupt*"))
            for item in quarantined:
                item.unlink(missing_ok=True)
            if path.exists():
                path.unlink()

        self.assertEqual(loaded, [])
        self.assertEqual(len(quarantined), 1)


if __name__ == "__main__":
    unittest.main()
