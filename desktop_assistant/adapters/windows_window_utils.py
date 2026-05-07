from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def normalize_path(value: str) -> str:
    if not value:
        return ""
    try:
        return str(Path(value).expanduser().resolve()).lower()
    except OSError:
        return str(Path(value).expanduser()).lower()


def normalize_keywords(keywords: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for keyword in keywords:
        item = str(keyword).strip().lower()
        if len(item) < 2:
            continue
        if item not in normalized:
            normalized.append(item)
    return normalized


_normalize_path = normalize_path
_normalize_keywords = normalize_keywords
