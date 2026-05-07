from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


def _extract_answer(payload: dict[str, Any]) -> str:
    for key in ("Answer", "AbstractText"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    related = payload.get("RelatedTopics")
    if isinstance(related, list):
        for item in related:
            text = _related_topic_text(item)
            if text:
                return text
    return ""


def _related_topic_text(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    text = item.get("Text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    nested = item.get("Topics")
    if isinstance(nested, list):
        for nested_item in nested:
            text = _related_topic_text(nested_item)
            if text:
                return text
    return ""


def _extract_source(payload: dict[str, Any]) -> str:
    for key in ("AbstractURL", "AbstractSource", "AnswerType"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_search_results(html_text: str) -> list[dict[str, str]]:
    title_matches = list(
        re.finditer(
            r'<a[^>]+class="[^"]*\bresult__a\b[^"]*"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
    )
    snippet_matches = list(
        re.finditer(
            r'<a[^>]+class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(?P<snippet>.*?)</a>',
            html_text,
            re.IGNORECASE | re.DOTALL,
        )
    )
    results: list[dict[str, str]] = []
    for index, title_match in enumerate(title_matches):
        title = _clean_html_text(title_match.group("title"))
        snippet = _clean_html_text(snippet_matches[index].group("snippet")) if index < len(snippet_matches) else ""
        if not title and not snippet:
            continue
        results.append(
            {
                "title": title,
                "snippet": snippet,
                "url": _clean_result_url(title_match.group("href")),
            }
        )
    return results


def _clean_html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(without_tags).split())


def _clean_result_url(href: str) -> str:
    decoded = unescape(href)
    parsed = urlparse(decoded)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return decoded
