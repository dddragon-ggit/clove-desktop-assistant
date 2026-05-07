from __future__ import annotations

from urllib.parse import quote_plus

import httpx

from ..capability.executor import execution_failed, execution_success
from ..models import ActionStep, ActionType, ExecutionStepResult
from .web_query_duckduckgo import _extract_answer, _extract_search_results, _extract_source
from .web_query_metadata import _answer_metadata
from .web_query_weather import _format_weather_answer, _looks_like_weather_query, _weather_location_from_query


class AnswerQueryHandler:
    """Read-only web-backed information lookup."""

    action_type = ActionType.ANSWER_QUERY
    handler_name = "web.answer_query"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 12.0) -> None:
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)

    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        query = action.target.strip()
        if not query:
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Query is empty.",
                code="QUERY_EMPTY",
                remedy="Provide a concrete information query.",
            )

        fallback_url = f"https://www.baidu.com/s?wd={quote_plus(query)}"
        lookup_errors: list[dict[str, str]] = []

        if _looks_like_weather_query(query):
            weather_answer = self._try_weather_query(query, lookup_errors)
            if weather_answer is not None:
                answer, source = weather_answer
                return execution_success(
                    action,
                    step_index,
                    f"[{trace_id}] Answer for {query}:\n{answer}\nSource: {source}",
                    metadata=_answer_metadata(
                        query=query,
                        answer=answer,
                        sources=[source],
                        confidence="high",
                        confidence_reason="天气接口返回了结构化的当前天气和今日温度字段。",
                        strategy="weather_endpoint",
                        fallback_url=fallback_url,
                        attempted_sources=self._attempted_sources(lookup_errors, "wttr.in"),
                    ),
                )

        instant_answer = self._try_duckduckgo_instant(query, lookup_errors)
        if instant_answer is not None:
            answer, source = instant_answer
            return execution_success(
                action,
                step_index,
                f"[{trace_id}] Answer for {query}:\n{answer}\nSource: {source}",
                    metadata=_answer_metadata(
                        query=query,
                        answer=answer,
                        sources=[source],
                        confidence="medium",
                        confidence_reason="搜索接口返回了直接答案，但未进行多来源交叉验证。",
                        strategy="duckduckgo_instant_answer",
                        fallback_url=fallback_url,
                        attempted_sources=self._attempted_sources(lookup_errors, "duckduckgo_instant"),
                    ),
                )

        snippet_answer = self._try_duckduckgo_snippets(query, lookup_errors)
        if snippet_answer is not None:
            answer, source = snippet_answer
            sources = [line for line in source.splitlines() if line.strip()]
            multi_source = len(dict.fromkeys(sources)) >= 2
            return execution_success(
                action,
                step_index,
                f"[{trace_id}] Answer for {query}:\n{answer}\nSource: {source}",
                    metadata=_answer_metadata(
                        query=query,
                        answer=answer,
                        sources=sources,
                        confidence="medium" if multi_source else "low",
                        confidence_reason=(
                            "多个网页摘要来源给出了可参考信息，但仍建议点开来源核对。"
                            if multi_source
                            else "只拿到了网页摘要片段，适合快速参考但需要点开来源确认。"
                        ),
                        strategy="duckduckgo_html_snippets",
                        fallback_url=fallback_url,
                        attempted_sources=self._attempted_sources(lookup_errors, "duckduckgo_html"),
                        fallback_reason="摘要可信度偏低时保留搜索页，方便继续核对。",
                    ),
                )

        if lookup_errors:
            return execution_failed(
                action,
                step_index,
                f"[{trace_id}] Information lookup failed for query: {query}",
                code="WEB_QUERY_TRANSPORT_ERROR",
                details={"query": query, "errors": lookup_errors, "fallback_url": fallback_url},
                remedy="Check network access, or open the fallback URL manually.",
                metadata=_answer_metadata(
                    query=query,
                    answer="",
                    sources=[],
                    confidence="none",
                    strategy="transport_error",
                    fallback_url=fallback_url,
                    attempted_sources=self._attempted_sources(lookup_errors),
                    fallback_reason="联网请求失败，只能提供搜索页作为降级入口。",
                    extra={"errors": lookup_errors},
                ),
            )

        return execution_failed(
            action,
            step_index,
            f"[{trace_id}] No direct answer was found for query: {query}",
            code="WEB_QUERY_NO_DIRECT_ANSWER",
            details={"query": query, "fallback_url": fallback_url},
            remedy="Open the fallback search URL or refine the query.",
            metadata=_answer_metadata(
                query=query,
                answer="",
                sources=[],
                confidence="none",
                strategy="no_direct_answer",
                fallback_url=fallback_url,
                attempted_sources=self._attempted_sources(lookup_errors, "duckduckgo_instant", "duckduckgo_html"),
                fallback_reason="没有找到可直接展示的答案，需要打开搜索结果继续确认。",
            ),
        )

    @staticmethod
    def _attempted_sources(lookup_errors: list[dict[str, str]], *current: str) -> list[str]:
        sources = [str(item.get("source") or "") for item in lookup_errors if item.get("source")]
        sources.extend(source for source in current if source)
        return list(dict.fromkeys(sources))

    def _try_weather_query(
        self,
        query: str,
        lookup_errors: list[dict[str, str]],
    ) -> tuple[str, str] | None:
        location = _weather_location_from_query(query)
        endpoint = f"https://wttr.in/{quote_plus(location)}?format=j1&lang=zh"
        try:
            response = self.client.get(endpoint)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            lookup_errors.append(
                {
                    "source": "wttr.in",
                    "endpoint": endpoint,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            return None

        answer = _format_weather_answer(location, payload)
        if not answer:
            lookup_errors.append(
                {
                    "source": "wttr.in",
                    "endpoint": endpoint,
                    "error_type": "NoWeatherAnswer",
                    "error": "Weather response did not contain usable current/today fields.",
                }
            )
            return None
        return answer, endpoint

    def _try_duckduckgo_instant(
        self,
        query: str,
        lookup_errors: list[dict[str, str]],
    ) -> tuple[str, str] | None:
        endpoint = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
        try:
            response = self.client.get(endpoint)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            lookup_errors.append(
                {
                    "source": "duckduckgo_instant",
                    "endpoint": endpoint,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            return None

        answer = _extract_answer(payload)
        if not answer:
            return None
        return answer, _extract_source(payload) or endpoint

    def _try_duckduckgo_snippets(
        self,
        query: str,
        lookup_errors: list[dict[str, str]],
    ) -> tuple[str, str] | None:
        endpoint = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            response = self.client.get(endpoint)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            lookup_errors.append(
                {
                    "source": "duckduckgo_html",
                    "endpoint": endpoint,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            return None

        results = _extract_search_results(response.text)
        if not results:
            return None
        lines = []
        sources = []
        for index, result in enumerate(results[:3], start=1):
            title = result.get("title") or "Result"
            snippet = result.get("snippet") or ""
            url = result.get("url") or endpoint
            lines.append(f"{index}. {title}: {snippet}")
            sources.append(url)
        return "\n".join(lines), "\n".join(dict.fromkeys(sources))
