from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class DiscoveredApplication:
    """A Windows application discovered from registry or Start Menu metadata."""

    name: str
    executable_path: str | None
    functions: tuple[str, ...]
    source: str
    install_location: str | None = None
    publisher: str | None = None
    version: str | None = None
    raw_target: str | None = None

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["functions"] = list(self.functions)
        return payload


@dataclass(frozen=True)
class ApplicationInventory:
    generated_at: str
    applications: list[DiscoveredApplication]

    def to_json(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "count": len(self.applications),
            "applications": [app.to_json() for app in self.applications],
        }

    def find(self, query: str) -> DiscoveredApplication | None:
        from .windows_app_matching import find_application

        return find_application(self.applications, query)


@dataclass(frozen=True)
class ApplicationNameIndex:
    """Compact app-name-only index used for cheap model-side intent matching."""

    generated_at: str
    names: list[str]

    def to_json(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "count": len(self.names),
            "names": self.names,
        }


class ApplicationDiscoveryProtocol(Protocol):
    def discover(self, *, include_start_menu: bool = True, limit: int | None = None) -> list[DiscoveredApplication]:
        """Return discovered applications."""
