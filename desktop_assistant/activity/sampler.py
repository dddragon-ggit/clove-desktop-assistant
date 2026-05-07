from __future__ import annotations

from collections.abc import Iterable

from ..adapters.windows_app_discovery import ApplicationInventoryStore
from ..adapters.windows_app_models import ApplicationInventory
from ..adapters.windows_window_state import WindowManagerProtocol, WindowsWindowManager
from ..projects.models import ProjectLocation
from ..projects.store import ProjectCatalogStore
from .models import ActivitySnapshot
from .process import ProcessMetadataProviderProtocol, WindowsProcessMetadataProvider
from .recent_files import RecentFileProviderProtocol, WindowsRecentFileProvider
from .resolver import ActivityResolver
from .store import ActivityStore


class DesktopActivitySampler:
    """Capture current app/file/project activity from non-invasive desktop metadata."""

    def __init__(
        self,
        *,
        window_manager: WindowManagerProtocol | None = None,
        app_inventory_store: ApplicationInventoryStore | None = None,
        project_catalog_store: ProjectCatalogStore | None = None,
        process_metadata_provider: ProcessMetadataProviderProtocol | None = None,
        recent_file_provider: RecentFileProviderProtocol | None = None,
        activity_store: ActivityStore | None = None,
    ) -> None:
        self.window_manager = window_manager or WindowsWindowManager()
        self.app_inventory_store = app_inventory_store or ApplicationInventoryStore()
        self.project_catalog_store = project_catalog_store or ProjectCatalogStore()
        self.process_metadata_provider = process_metadata_provider or WindowsProcessMetadataProvider()
        self.recent_file_provider = recent_file_provider or WindowsRecentFileProvider()
        self.activity_store = activity_store or ActivityStore()

    def sample(self) -> ActivitySnapshot:
        notes: list[str] = []
        window = None
        if self.window_manager.is_available():
            try:
                window = self.window_manager.get_foreground_window()
            except Exception as exc:  # noqa: BLE001 - desktop access can be denied
                notes.append(f"foreground_window_unavailable: {type(exc).__name__}: {exc}")
        else:
            notes.append("window_manager_unavailable")

        command_line = ""
        if window is not None:
            command_line = self.process_metadata_provider.get_command_line(window.process_id)

        inventory = self._load_inventory(notes)
        projects = self._load_projects(notes)
        recent_files = self.recent_file_provider.list_recent_files(limit=20)
        resolver = ActivityResolver(inventory=inventory, projects=projects)
        return resolver.resolve(
            window=window,
            command_line=command_line,
            recent_files=recent_files,
            notes=notes,
        )

    def sample_and_store(self, *, max_records: int = 500) -> ActivitySnapshot:
        return self.activity_store.append(self.sample(), max_records=max_records)

    def _load_inventory(self, notes: list[str]) -> ApplicationInventory | None:
        try:
            return self.app_inventory_store.ensure(refresh=False)
        except Exception as exc:  # noqa: BLE001 - inventory is a helpful signal, not a hard dependency
            notes.append(f"app_inventory_unavailable: {type(exc).__name__}: {exc}")
            return None

    def _load_projects(self, notes: list[str]) -> Iterable[ProjectLocation]:
        try:
            return self.project_catalog_store.ensure()
        except Exception as exc:  # noqa: BLE001 - project catalog is optional context
            notes.append(f"project_catalog_unavailable: {type(exc).__name__}: {exc}")
            return []
