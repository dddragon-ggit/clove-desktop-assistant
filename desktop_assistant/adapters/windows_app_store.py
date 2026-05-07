from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..storage import quarantine_corrupted_file, write_json_atomic
from .windows_app_matching import _unique_sorted_names, build_app_name_index
from .windows_app_models import (
    ApplicationDiscoveryProtocol,
    ApplicationInventory,
    ApplicationNameIndex,
    DiscoveredApplication,
)
from .windows_app_scanner import WindowsApplicationDiscovery


def default_app_inventory_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "app_inventory.json"


def default_app_name_index_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "app_name_index.json"


class ApplicationInventoryStore:
    """Persist discovered app inventory so startup does not rescan every time."""

    def __init__(self, path: str | Path | None = None, name_index_path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_app_inventory_path()
        if name_index_path is not None:
            self.name_index_path = Path(name_index_path)
        elif path is None:
            self.name_index_path = default_app_name_index_path()
        else:
            self.name_index_path = self.path.with_name(f"{self.path.stem}_name_index.json")

    def ensure(
        self,
        *,
        discovery: ApplicationDiscoveryProtocol | None = None,
        refresh: bool = False,
        include_start_menu: bool = True,
        limit: int | None = None,
    ) -> ApplicationInventory:
        if self.path.exists() and not refresh:
            try:
                inventory = self.load()
                self.ensure_name_index(inventory)
                return inventory
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError):
                pass

        scanner = discovery or WindowsApplicationDiscovery()
        applications = scanner.discover(include_start_menu=include_start_menu, limit=limit)
        inventory = ApplicationInventory(
            generated_at=datetime.now(UTC).isoformat(),
            applications=applications,
        )
        self.save(inventory)
        return inventory

    def load(self) -> ApplicationInventory:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            quarantine_corrupted_file(
                self.path,
                source="app_inventory_store",
                category="app_inventory_corrupted",
                reason="App inventory JSON is unreadable.",
            )
            raise ValueError(f"App inventory is unreadable: {self.path}") from exc
        try:
            applications = [
                DiscoveredApplication(
                    name=str(item.get("name") or ""),
                    executable_path=item.get("executable_path"),
                    functions=tuple(item.get("functions") or ()),
                    source=str(item.get("source") or "cache"),
                    install_location=item.get("install_location"),
                    publisher=item.get("publisher"),
                    version=item.get("version"),
                    raw_target=item.get("raw_target"),
                )
                for item in payload.get("applications", [])
                if isinstance(item, dict)
            ]
        except Exception as exc:
            quarantine_corrupted_file(
                self.path,
                source="app_inventory_store",
                category="app_inventory_invalid",
                reason="App inventory items could not be validated.",
            )
            raise ValueError(f"App inventory is invalid: {self.path}") from exc
        return ApplicationInventory(
            generated_at=str(payload.get("generated_at") or ""),
            applications=applications,
        )

    def save(self, inventory: ApplicationInventory) -> None:
        write_json_atomic(self.path, inventory.to_json())
        self.save_name_index(build_app_name_index(inventory))

    def load_name_index(self) -> ApplicationNameIndex:
        try:
            payload = json.loads(self.name_index_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            quarantine_corrupted_file(
                self.name_index_path,
                source="app_inventory_store",
                category="app_name_index_corrupted",
                reason="App name index JSON is unreadable.",
            )
            raise ValueError(f"App name index is unreadable: {self.name_index_path}") from exc
        names = [str(name).strip() for name in payload.get("names", []) if str(name).strip()]
        return ApplicationNameIndex(
            generated_at=str(payload.get("generated_at") or ""),
            names=_unique_sorted_names(names),
        )

    def save_name_index(self, index: ApplicationNameIndex) -> None:
        write_json_atomic(self.name_index_path, index.to_json())

    def ensure_name_index(self, inventory: ApplicationInventory | None = None) -> ApplicationNameIndex:
        if self.name_index_path.exists():
            try:
                return self.load_name_index()
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError):
                pass
        source_inventory = inventory if inventory is not None else self.load()
        index = build_app_name_index(source_inventory)
        self.save_name_index(index)
        return index


def ensure_default_app_inventory(*, refresh: bool = False) -> ApplicationInventory:
    return ApplicationInventoryStore().ensure(refresh=refresh)
