from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .defaults import default_project_roots
from .matching import merge_project_locations
from .models import ProjectLocation


def discover_project_locations(
    *,
    roots: Iterable[str | Path] | None = None,
    max_depth: int = 2,
    limit: int = 80,
) -> list[ProjectLocation]:
    discovered: list[ProjectLocation] = []
    seen_paths: set[str] = set()
    safe_limit = max(1, min(limit, 500))
    for root in roots or default_project_roots():
        root_path = Path(root).expanduser()
        if not root_path.exists() or not root_path.is_dir():
            continue
        pending: list[tuple[Path, int]] = [(root_path, 0)]
        while pending and len(discovered) < safe_limit:
            directory, depth = pending.pop(0)
            if ignored_project_dir(directory):
                continue
            resolved = safe_resolved_path(directory)
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)

            markers = project_markers(directory)
            if markers:
                discovered.append(
                    ProjectLocation(
                        name=directory.name or str(directory),
                        path=str(directory),
                        kind="project",
                        description="Auto-discovered project markers: " + ", ".join(markers[:4]),
                    )
                )
            if depth >= max_depth:
                continue
            try:
                children = sorted(
                    (child for child in directory.iterdir() if child.is_dir()),
                    key=lambda item: item.name.lower(),
                )
            except OSError:
                continue
            pending.extend((child, depth + 1) for child in children if not ignored_project_dir(child))
    return merge_project_locations(discovered)


def project_markers(directory: Path) -> list[str]:
    marker_names = (
        ".git",
        ".code-workspace",
        "pyproject.toml",
        "package.json",
        "requirements.txt",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
    )
    markers = []
    for marker in marker_names:
        if marker == ".code-workspace":
            try:
                if any(directory.glob("*.code-workspace")):
                    markers.append("*.code-workspace")
            except OSError:
                pass
            continue
        if (directory / marker).exists():
            markers.append(marker)
    return markers


def ignored_project_dir(directory: Path) -> bool:
    name = directory.name.lower()
    return (
        name.startswith(".")
        and name not in {".config"}
    ) or name in {
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "dist",
        "build",
        "target",
        ".git",
    }


def safe_resolved_path(directory: Path) -> str:
    try:
        return str(directory.resolve())
    except OSError:
        return str(directory.absolute())


_project_markers = project_markers
_ignored_project_dir = ignored_project_dir
_safe_resolved_path = safe_resolved_path
