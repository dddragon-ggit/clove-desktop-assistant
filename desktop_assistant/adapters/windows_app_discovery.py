from __future__ import annotations

import json

from .windows_app_matching import (
    _app_quality,
    _merge_applications,
    _merge_key,
    _unique_sorted_names,
    build_app_name_index,
    find_application,
)
from .windows_app_models import (
    ApplicationDiscoveryProtocol,
    ApplicationInventory,
    ApplicationNameIndex,
    DiscoveredApplication,
)
from .windows_app_normalization import (
    _display_name_from_executable,
    _infer_application_functions,
    _is_generic_search_token,
    _is_uninstall_or_setup_name,
    _normalize_name,
    _search_tokens,
)
from .windows_app_scan_helpers import (
    _executable_rank,
    _extract_executable_path,
    _find_executable_in_install_location,
    _is_unsafe_executable_path,
    _resolve_shortcut_target,
    _start_menu_roots,
)
from .windows_app_scanner import WindowsApplicationDiscovery
from .windows_app_store import (
    ApplicationInventoryStore,
    default_app_inventory_path,
    default_app_name_index_path,
    ensure_default_app_inventory,
)
from .windows_registry_helpers import (
    _NullContext,
    _enum_subkeys,
    _open_registry_key,
    _query_registry_value,
    _winreg,
)

__all__ = [
    "ApplicationDiscoveryProtocol",
    "ApplicationInventory",
    "ApplicationInventoryStore",
    "ApplicationNameIndex",
    "DiscoveredApplication",
    "WindowsApplicationDiscovery",
    "build_app_name_index",
    "default_app_inventory_path",
    "default_app_name_index_path",
    "ensure_default_app_inventory",
    "find_application",
]


def main() -> int:
    inventory = ApplicationInventoryStore().ensure(refresh=True)
    print(json.dumps(inventory.to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
