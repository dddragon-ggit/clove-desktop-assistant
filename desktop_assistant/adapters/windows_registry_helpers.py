from __future__ import annotations

from typing import Iterable


def _winreg():
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None
    return winreg


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


def _open_registry_key(winreg, hive_or_key, key_path: str):
    try:
        return winreg.OpenKey(hive_or_key, key_path, 0, winreg.KEY_READ)
    except OSError:
        return _NullContext()


def _enum_subkeys(winreg, key) -> Iterable[str]:
    index = 0
    while True:
        try:
            yield winreg.EnumKey(key, index)
        except OSError:
            return
        index += 1


def _query_registry_value(winreg, key, value_name: str) -> str | None:
    try:
        value, _value_type = winreg.QueryValueEx(key, value_name)
    except OSError:
        return None
    if value is None:
        return None
    return str(value).strip() or None
