from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from ..storage import quarantine_corrupted_file, write_json_atomic
from .defaults import default_project_catalog_path, default_project_locations
from .discovery import discover_project_locations
from .matching import find_project_location, merge_project_locations, normalize_project_text
from .models import PROJECT_CATALOG_SCHEMA_VERSION, ProjectLocation


class ProjectCatalogStore:
    """A small editable catalog for fast folder/project location."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_project_catalog_path()

    def ensure(self) -> list[ProjectLocation]:
        locations = self.load() if self.path.exists() else []
        merged = merge_project_locations((*default_project_locations(), *locations))
        self.save(merged)
        return merged

    def load(self) -> list[ProjectLocation]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            quarantine_corrupted_file(self.path, source="project_catalog_store", category="project_catalog_corrupted", reason="Project catalog JSON is unreadable.")
            return []
        if not isinstance(payload, dict):
            quarantine_corrupted_file(self.path, source="project_catalog_store", category="project_catalog_invalid", reason="Project catalog root must be an object.")
            return []
        raw_locations = payload.get("projects") or []
        if not isinstance(raw_locations, list):
            quarantine_corrupted_file(self.path, source="project_catalog_store", category="project_catalog_invalid", reason="Project catalog projects must be a list.")
            return []
        try:
            return [
                ProjectLocation.from_json(item)
                for item in raw_locations
                if isinstance(item, dict)
            ]
        except Exception:
            quarantine_corrupted_file(self.path, source="project_catalog_store", category="project_catalog_invalid", reason="Project catalog items could not be validated.")
            return []

    def save(self, locations: Iterable[ProjectLocation]) -> None:
        payload = {
            "schema_version": PROJECT_CATALOG_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "projects": [location.to_json() for location in locations],
        }
        write_json_atomic(self.path, payload)

    def find(self, query: str) -> ProjectLocation | None:
        locations = self.ensure()
        return find_project_location(locations, query)

    def refresh_discovered(
        self,
        *,
        roots: Iterable[str | Path] | None = None,
        max_depth: int = 2,
        limit: int = 80,
    ) -> list[ProjectLocation]:
        locations = self.ensure()
        discovered = discover_project_locations(roots=roots, max_depth=max_depth, limit=limit)
        merged = merge_project_locations((*locations, *discovered))
        self.save(merged)
        return merged

    def upsert(self, location: ProjectLocation) -> ProjectLocation:
        locations = self.ensure()
        by_name = {normalize_project_text(item.name): item for item in locations}
        by_name[normalize_project_text(location.name)] = location
        merged = merge_project_locations(by_name.values())
        self.save(merged)
        return location

    def delete(self, name: str) -> bool:
        normalized = normalize_project_text(name)
        locations = self.load() if self.path.exists() else []
        kept = [location for location in locations if normalize_project_text(location.name) != normalized]
        if len(kept) == len(locations):
            return False
        self.save(kept)
        return True
