from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from .windows_app_models import ApplicationInventory, ApplicationNameIndex, DiscoveredApplication
from .windows_app_normalization import _is_uninstall_or_setup_name, _normalize_name, _search_tokens
from .windows_app_scan_helpers import _is_unsafe_executable_path


def _merge_applications(apps: Iterable[DiscoveredApplication]) -> list[DiscoveredApplication]:
    merged: dict[str, DiscoveredApplication] = {}
    for app in apps:
        if not app.name.strip():
            continue
        if _is_uninstall_or_setup_name(app.name) or _is_unsafe_executable_path(app.executable_path):
            continue
        key = _merge_key(app)
        current = merged.get(key)
        if current is None or _app_quality(app) > _app_quality(current):
            merged[key] = app
    return sorted(merged.values(), key=lambda app: app.name.lower())


def build_app_name_index(inventory: ApplicationInventory) -> ApplicationNameIndex:
    """Create the compact model-facing table that contains only display names."""

    return ApplicationNameIndex(
        generated_at=inventory.generated_at,
        names=_unique_sorted_names(app.name for app in inventory.applications),
    )


def _unique_sorted_names(names: Iterable[str]) -> list[str]:
    unique: dict[str, str] = {}
    for name in names:
        stripped = str(name).strip()
        if not stripped:
            continue
        normalized = _normalize_name(stripped)
        if not normalized:
            continue
        unique.setdefault(normalized, stripped)
    return sorted(unique.values(), key=lambda item: item.lower())


def find_application(apps: Iterable[DiscoveredApplication], query: str) -> DiscoveredApplication | None:
    """Return the best inventory app match for a user/model target string."""

    query_norm = _normalize_name(query)
    if not query_norm:
        return None
    query_tokens = _search_tokens(query)
    best_app: DiscoveredApplication | None = None
    best_score: tuple[int, tuple[int, int, int], str] | None = None

    for app in apps:
        if not app.executable_path or _is_unsafe_executable_path(app.executable_path):
            continue
        candidate = " ".join(
            part
            for part in [
                app.name,
                app.executable_path or "",
                app.install_location or "",
                app.raw_target or "",
            ]
            if part
        )
        candidate_norm = _normalize_name(candidate)
        app_name_norm = _normalize_name(app.name)
        score = 0
        if app_name_norm == query_norm:
            score += 100
        if query_norm in candidate_norm:
            score += 70
        if app_name_norm and app_name_norm in query_norm:
            score += 50
        score += 12 * sum(1 for token in query_tokens if token in candidate_norm)

        if score <= 0:
            continue
        ranked_score = (score, _app_quality(app), app.name.lower())
        if best_score is None or ranked_score > best_score:
            best_score = ranked_score
            best_app = app
    return best_app


def suggest_applications(apps: Iterable[DiscoveredApplication], query: str, *, limit: int = 3) -> list[DiscoveredApplication]:
    """Return nearby app names for a failed lookup without treating them as exact matches."""

    query_norm = _normalize_name(query)
    if not query_norm:
        return []
    scored: list[tuple[int, tuple[int, int, int], str, DiscoveredApplication]] = []
    for app in apps:
        if not app.executable_path or _is_unsafe_executable_path(app.executable_path):
            continue
        app_name_norm = _normalize_name(app.name)
        candidate_norm = _normalize_name(
            " ".join(part for part in [app.name, app.executable_path or "", app.install_location or ""] if part)
        )
        score = 0
        if query_norm in candidate_norm or app_name_norm in query_norm:
            score += 70
        score += 12 * sum(1 for token in _search_tokens(query) if token in candidate_norm)
        if app_name_norm:
            score += round(42 * SequenceMatcher(None, query_norm, app_name_norm).ratio())
        if score < 20:
            continue
        scored.append((score, _app_quality(app), app.name.lower(), app))
    scored.sort(reverse=True)
    return [item[-1] for item in scored[:limit]]


def _merge_key(app: DiscoveredApplication) -> str:
    if app.executable_path:
        return str(Path(app.executable_path)).lower()
    return _normalize_name(app.name)


def _app_quality(app: DiscoveredApplication) -> tuple[int, int, int]:
    has_exe = 1 if app.executable_path else 0
    source_score = {
        "registry_app_paths": 3,
        "start_menu_shortcut": 2,
        "registry_uninstall": 1,
    }.get(app.source, 0)
    has_metadata = sum(1 for value in (app.publisher, app.version, app.install_location) if value)
    return (has_exe, source_score, has_metadata)
