from __future__ import annotations

import os
import re
from pathlib import Path

from .windows_app_normalization import _normalize_name


def _extract_executable_path(raw_value: str | None) -> str | None:
    if not raw_value:
        return None

    expanded = os.path.expandvars(raw_value.strip())
    quoted = re.search(r'"(?P<path>[^"]+\.exe)"', expanded, re.IGNORECASE)
    if quoted is not None:
        return quoted.group("path")

    unquoted = re.search(r"(?P<path>[A-Za-z]:\\[^\r\n,;]+?\.exe)", expanded, re.IGNORECASE)
    if unquoted is not None:
        return unquoted.group("path").strip()

    if expanded.lower().endswith(".exe"):
        return expanded.strip()
    return None


def _is_unsafe_executable_path(path: str | None) -> bool:
    if not path:
        return False
    lowered = Path(path).stem.lower()
    unsafe_markers = ("unins", "uninstall", "setup", "installer", "install", "updater", "update", "cleanup")
    return any(marker in lowered for marker in unsafe_markers)


def _find_executable_in_install_location(app_name: str, install_location: str | None) -> str | None:
    if not install_location:
        return None
    root = Path(os.path.expandvars(install_location.strip()))
    if not root.exists() or not root.is_dir():
        return None

    try:
        candidates = [path for path in root.glob("*.exe") if path.is_file()]
    except OSError:
        return None
    if not candidates:
        try:
            candidates = [path for path in root.glob("*/*.exe") if path.is_file()]
        except OSError:
            return None

    candidates = [path for path in candidates if not _is_unsafe_executable_path(str(path))]
    ranked = sorted(candidates, key=lambda path: _executable_rank(app_name, path))
    return str(ranked[0]) if ranked else None


def _executable_rank(app_name: str, path: Path) -> tuple[int, int, int, str]:
    lowered_name = _normalize_name(app_name)
    lowered_stem = _normalize_name(path.stem)
    bad_markers = ("unins", "uninstall", "update", "crash", "helper", "setup", "installer", "install")
    bad_score = 1 if any(marker in lowered_stem for marker in bad_markers) else 0
    name_score = 0 if lowered_stem and lowered_stem in lowered_name else 1
    return (bad_score, name_score, len(path.name), path.name.lower())


def _resolve_shortcut_target(shortcut_path: Path) -> str | None:
    try:
        import win32com.client  # type: ignore[import-not-found]

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(shortcut_path))
        target = getattr(shortcut, "Targetpath", None)
    except Exception:  # noqa: BLE001 - shortcut resolution is best-effort
        return None
    return _extract_executable_path(target)


def _start_menu_roots() -> list[Path]:
    roots: list[Path] = []
    program_data = os.environ.get("ProgramData")
    app_data = os.environ.get("APPDATA")
    if program_data:
        roots.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if app_data:
        roots.append(Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return roots
