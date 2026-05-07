from __future__ import annotations

from collections.abc import Iterable

from .models import ProjectLocation


def merge_project_locations(locations: Iterable[ProjectLocation]) -> list[ProjectLocation]:
    merged: dict[str, ProjectLocation] = {}
    for location in locations:
        if not location.name.strip() or not location.path.strip():
            continue
        key = normalize_project_text(location.name)
        merged[key] = location
    return sorted(merged.values(), key=lambda item: item.name.lower())


def find_project_location(locations: Iterable[ProjectLocation], query: str) -> ProjectLocation | None:
    normalized_query = normalize_project_text(query)
    if not normalized_query:
        return None

    aliases = {
        "桌面": "desktop",
        "desktop": "desktop",
        "下载": "downloads",
        "下载目录": "downloads",
        "downloads": "downloads",
        "文档": "documents",
        "documents": "documents",
        "当前项目": "current workspace",
        "当前工程": "current workspace",
        "workspace": "current workspace",
    }
    normalized_query = normalize_project_text(aliases.get(query.strip().lower(), query))

    best_location: ProjectLocation | None = None
    best_score = 0
    for location in locations:
        candidate = " ".join([location.name, location.path, location.description])
        normalized_candidate = normalize_project_text(candidate)
        normalized_name = normalize_project_text(location.name)
        score = 0
        if normalized_name == normalized_query:
            score += 100
        if normalized_query in normalized_candidate:
            score += 60
        if normalized_name and normalized_name in normalized_query:
            score += 40
        for token in normalized_query.split():
            if token and token in normalized_candidate:
                score += 10
        if score >= 40 and score > best_score:
            best_score = score
            best_location = location
    return best_location


def normalize_project_text(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").replace("-", " ").split())


_normalize = normalize_project_text
