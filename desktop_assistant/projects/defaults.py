from __future__ import annotations

from pathlib import Path

from .models import ProjectLocation


def default_project_catalog_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "projects.json"


def default_project_locations() -> tuple[ProjectLocation, ...]:
    home = Path.home()
    cwd = Path.cwd()
    candidates = [
        ProjectLocation("current workspace", str(cwd), "project", "Current assistant workspace."),
        ProjectLocation("desktop", str(home / "Desktop"), "folder", "User desktop folder."),
        ProjectLocation("downloads", str(home / "Downloads"), "folder", "User downloads folder."),
        ProjectLocation("documents", str(home / "Documents"), "folder", "User documents folder."),
    ]
    return tuple(location for location in candidates if location.path)


def default_project_roots() -> tuple[Path, ...]:
    home = Path.home()
    cwd = Path.cwd()
    candidates = [
        cwd,
        cwd.parent,
        home / "Projects",
        home / "Code",
        home / "source",
        home / "repos",
        home / "Desktop",
        home / "Documents",
    ]
    return tuple(dict.fromkeys(candidates))


_default_project_roots = default_project_roots
