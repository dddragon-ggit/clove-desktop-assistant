from __future__ import annotations

import json
import re
from pathlib import Path

from ..adapters.windows_app_discovery import ApplicationInventoryStore


def load_app_inventory_summary(*, limit: int = 40, path: str | Path | None = None, query: str | None = None) -> str:
    store = ApplicationInventoryStore(path=path)
    if not store.path.exists():
        return "No app inventory cache found yet."

    try:
        inventory = store.load()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return f"App inventory cache is unavailable: {type(exc).__name__}: {exc}"

    lines = [f"generated_at={inventory.generated_at}; count={len(inventory.applications)}"]
    relevant = relevant_inventory_matches(inventory, query)
    if relevant:
        lines.append("Relevant app matches for this request:")
        for app in relevant:
            functions = ", ".join(app.functions)
            executable = app.executable_path or "(unknown executable)"
            lines.append(f"- {app.name} | functions={functions} | executable={executable}")
        lines.append("General app inventory sample:")
    for app in inventory.applications[:limit]:
        functions = ", ".join(app.functions)
        executable = app.executable_path or "(unknown executable)"
        lines.append(f"- {app.name} | functions={functions} | executable={executable}")
    if len(inventory.applications) > limit:
        lines.append(f"... {len(inventory.applications) - limit} more apps omitted")
    return "\n".join(lines)


def load_app_name_index_summary(
    *,
    limit: int = 300,
    path: str | Path | None = None,
    name_index_path: str | Path | None = None,
) -> str:
    store = ApplicationInventoryStore(path=path, name_index_path=name_index_path)
    try:
        index = store.ensure_name_index()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return f"App name index is unavailable: {type(exc).__name__}: {exc}"

    lines = [f"generated_at={index.generated_at}; count={len(index.names)}"]
    selected_names = index.names[:limit]
    lines.extend(f"- {name}" for name in selected_names)
    if len(index.names) > limit:
        lines.append(f"... {len(index.names) - limit} more app names omitted")
    return "\n".join(lines)


def load_app_candidate_summary(
    *,
    query: str,
    limit: int = 5,
    path: str | Path | None = None,
    name_index_path: str | Path | None = None,
) -> str:
    store = ApplicationInventoryStore(path=path, name_index_path=name_index_path)
    try:
        inventory = store.ensure(refresh=False)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return f"High-relevance app candidates are unavailable: {type(exc).__name__}: {exc}"

    candidates = relevant_inventory_matches(inventory, query, limit=limit)
    if not candidates:
        return "No high-relevance app candidates were found for this request."

    lines = ["High-relevance app candidates for this request:"]
    for app in candidates:
        functions = ", ".join(app.functions)
        executable = app.executable_path or "(unknown executable)"
        lines.append(f"- {app.name} | functions={functions} | executable={executable}")
    return "\n".join(lines)


def relevant_inventory_matches(inventory, query: str | None, *, limit: int = 5):
    if not query:
        return []
    matches = []
    for target in [query, *query_fragments(query)]:
        app = inventory.find(target)
        if app is None:
            continue
        if app.name not in {match.name for match in matches}:
            matches.append(app)
        if len(matches) >= limit:
            break
    return matches


def query_fragments(query: str) -> list[str]:
    fragments: list[str] = []
    for token in re.findall(r"[a-z0-9.]+|[\u4e00-\u9fff]+", query.lower()):
        if len(token) >= 2:
            fragments.append(token)
        if re.search(r"[\u4e00-\u9fff]", token) and len(token) > 2:
            for size in (2, 3, 4):
                for index in range(0, len(token) - size + 1):
                    fragment = token[index : index + size]
                    if fragment not in fragments:
                        fragments.append(fragment)
    return fragments


_relevant_inventory_matches = relevant_inventory_matches
_query_fragments = query_fragments
