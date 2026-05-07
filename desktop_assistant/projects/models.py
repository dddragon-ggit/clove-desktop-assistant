from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROJECT_CATALOG_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProjectLocation:
    name: str
    path: str
    kind: str = "folder"
    description: str = ""

    def to_json(self) -> dict[str, str]:
        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "description": self.description,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ProjectLocation":
        return cls(
            name=str(payload.get("name") or ""),
            path=str(payload.get("path") or ""),
            kind=str(payload.get("kind") or "folder"),
            description=str(payload.get("description") or ""),
        )
