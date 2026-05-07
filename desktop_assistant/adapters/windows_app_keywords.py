from __future__ import annotations

import re
from pathlib import Path


def app_window_keywords(app_name: str, executable_path: str) -> list[str]:
    values = [app_name]
    path = Path(executable_path)
    values.extend([path.stem, path.parent.name])
    keywords: list[str] = []
    for value in values:
        lowered = value.strip().lower()
        if lowered:
            append_keyword(keywords, lowered)
        simplified = re.sub(r"\b(launcher|client|app|application)\b", "", lowered).strip(" .-_")
        if simplified:
            append_keyword(keywords, simplified)
        for token in re.findall(r"[a-z0-9.]+|[\u4e00-\u9fff]+", lowered):
            if useful_window_keyword(token):
                append_keyword(keywords, token.lower())
            if re.search(r"[\u4e00-\u9fff]", token) and len(token) > 2:
                for size in (2, 3, 4):
                    for index in range(0, len(token) - size + 1):
                        append_keyword(keywords, token[index : index + size])
    if "战网" in app_name and "battle.net" not in keywords:
        append_keyword(keywords, "battle.net")
        append_keyword(keywords, "battle")
    return keywords


def append_keyword(keywords: list[str], keyword: str) -> None:
    item = keyword.strip().lower()
    if useful_window_keyword(item) and item not in keywords:
        keywords.append(item)


def useful_window_keyword(keyword: str) -> bool:
    if keyword in {"qq", "wx", "tm"}:
        return True
    if keyword in {"launcher", "client", "application"}:
        return False
    if re.search(r"[\u4e00-\u9fff]", keyword):
        return len(keyword) >= 2
    return len(keyword) >= 4
