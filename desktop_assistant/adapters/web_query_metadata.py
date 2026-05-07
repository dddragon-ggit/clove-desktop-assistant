from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse


def _answer_metadata(
    *,
    query: str,
    answer: str,
    sources: list[str],
    confidence: str,
    strategy: str,
    fallback_url: str,
    attempted_sources: list[str] | None = None,
    confidence_reason: str = "",
    fallback_reason: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_sources = [source for source in dict.fromkeys(sources) if source]
    clean_attempts = [source for source in dict.fromkeys(attempted_sources or sources) if source]
    cross_check_sources = _source_domains(clean_sources)
    metadata = {
        "query": query,
        "answer": answer,
        "sources": clean_sources,
        "source_count": len(clean_sources),
        "cross_check_sources": cross_check_sources,
        "cross_check_source_count": len(cross_check_sources),
        "verification_status": _verification_status(confidence, clean_sources, cross_check_sources),
        "source_summary": _source_summary(clean_attempts, clean_sources, cross_check_sources),
        "attempted_sources": clean_attempts,
        "attempted_source_count": len(clean_attempts),
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "strategy": strategy,
        "fallback_url": fallback_url,
        "fallback_reason": fallback_reason,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    if extra:
        metadata.update(extra)
    return metadata


def _source_domains(sources: list[str]) -> list[str]:
    domains = []
    for source in sources:
        parsed = urlparse(source if "://" in source else f"https://{source}")
        domain = parsed.netloc or parsed.path.split("/")[0]
        if domain:
            domains.append(domain.lower())
    return list(dict.fromkeys(domains))


def _verification_status(confidence: str, sources: list[str], domains: list[str]) -> str:
    if not sources:
        return "no_direct_source"
    if confidence == "high":
        return "structured_source"
    if len(domains) >= 2:
        return "multi_source_summary"
    if confidence == "medium":
        return "single_direct_source"
    return "single_snippet_source"


def _source_summary(attempts: list[str], sources: list[str], domains: list[str]) -> str:
    if not sources:
        return f"已尝试 {len(attempts)} 个查询入口，但没有拿到可直接展示的来源。"
    if len(domains) >= 2:
        return f"已从 {len(domains)} 个不同来源提取摘要，适合快速参考。"
    return f"已从 1 个来源提取结果，建议需要精确结论时点开来源核对。"
