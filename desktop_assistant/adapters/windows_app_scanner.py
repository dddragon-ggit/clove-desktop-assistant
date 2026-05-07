from __future__ import annotations

from .windows_app_matching import _merge_applications
from .windows_app_models import DiscoveredApplication
from .windows_app_normalization import (
    _display_name_from_executable,
    _infer_application_functions,
    _is_uninstall_or_setup_name,
)
from .windows_app_scan_helpers import (
    _extract_executable_path,
    _find_executable_in_install_location,
    _is_unsafe_executable_path,
    _resolve_shortcut_target,
    _start_menu_roots,
)
from .windows_registry_helpers import _enum_subkeys, _open_registry_key, _query_registry_value, _winreg


class WindowsApplicationDiscovery:
    """Discover installed Windows apps and best-effort executable paths.

    The registry is the primary source. Start Menu shortcuts are used as a
    second source because many user-facing apps register shortcuts more reliably
    than App Paths.
    """

    UNINSTALL_KEYS = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    )
    APP_PATHS_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"

    def discover(self, *, include_start_menu: bool = True, limit: int | None = None) -> list[DiscoveredApplication]:
        apps: list[DiscoveredApplication] = []
        apps.extend(self._discover_app_paths())
        apps.extend(self._discover_uninstall_entries())
        if include_start_menu:
            apps.extend(self._discover_start_menu_shortcuts())

        merged = _merge_applications(apps)
        if limit is not None:
            return merged[: max(0, limit)]
        return merged

    def _discover_app_paths(self) -> list[DiscoveredApplication]:
        winreg = _winreg()
        if winreg is None:
            return []

        apps: list[DiscoveredApplication] = []
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            with _open_registry_key(winreg, hive, self.APP_PATHS_KEY) as key:
                if key is None:
                    continue
                for subkey_name in _enum_subkeys(winreg, key):
                    with _open_registry_key(winreg, key, subkey_name) as subkey:
                        if subkey is None:
                            continue
                        raw_target = _query_registry_value(winreg, subkey, "")
                        executable = _extract_executable_path(raw_target or subkey_name)
                        if executable is None and subkey_name.lower().endswith(".exe"):
                            executable = _extract_executable_path(subkey_name)
                        apps.append(
                            DiscoveredApplication(
                                name=_display_name_from_executable(subkey_name),
                                executable_path=executable,
                                functions=_infer_application_functions(
                                    _display_name_from_executable(subkey_name),
                                    executable,
                                ),
                                source="registry_app_paths",
                                install_location=_query_registry_value(winreg, subkey, "Path"),
                                raw_target=raw_target,
                            )
                        )
        return apps

    def _discover_uninstall_entries(self) -> list[DiscoveredApplication]:
        winreg = _winreg()
        if winreg is None:
            return []

        apps: list[DiscoveredApplication] = []
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key_path in self.UNINSTALL_KEYS:
                with _open_registry_key(winreg, hive, key_path) as key:
                    if key is None:
                        continue
                    for subkey_name in _enum_subkeys(winreg, key):
                        with _open_registry_key(winreg, key, subkey_name) as subkey:
                            if subkey is None:
                                continue
                            name = _query_registry_value(winreg, subkey, "DisplayName")
                            if not name:
                                continue
                            display_icon = _query_registry_value(winreg, subkey, "DisplayIcon")
                            install_location = _query_registry_value(winreg, subkey, "InstallLocation")
                            executable = _extract_executable_path(display_icon)
                            if _is_unsafe_executable_path(executable):
                                executable = None
                            if executable is None:
                                executable = _find_executable_in_install_location(name, install_location)
                            apps.append(
                                DiscoveredApplication(
                                    name=name.strip(),
                                    executable_path=executable,
                                    functions=_infer_application_functions(name, executable),
                                    source="registry_uninstall",
                                    install_location=install_location,
                                    publisher=_query_registry_value(winreg, subkey, "Publisher"),
                                    version=_query_registry_value(winreg, subkey, "DisplayVersion"),
                                    raw_target=display_icon,
                                )
                            )
        return apps

    def _discover_start_menu_shortcuts(self) -> list[DiscoveredApplication]:
        apps: list[DiscoveredApplication] = []
        for root in _start_menu_roots():
            if not root.exists():
                continue
            try:
                shortcuts = root.rglob("*.lnk")
                for shortcut in shortcuts:
                    executable = _resolve_shortcut_target(shortcut)
                    if executable is None:
                        continue
                    if _is_uninstall_or_setup_name(shortcut.stem) or _is_unsafe_executable_path(executable):
                        continue
                    apps.append(
                        DiscoveredApplication(
                            name=shortcut.stem,
                            executable_path=executable,
                            functions=_infer_application_functions(shortcut.stem, executable),
                            source="start_menu_shortcut",
                            raw_target=str(shortcut),
                        )
                    )
            except OSError:
                continue
        return apps
