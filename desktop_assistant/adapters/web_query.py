from __future__ import annotations

from .web_query_duckduckgo import (
    _clean_html_text,
    _clean_result_url,
    _extract_answer,
    _extract_search_results,
    _extract_source,
    _related_topic_text,
)
from .web_query_handler import AnswerQueryHandler
from .web_query_metadata import _answer_metadata
from .web_query_weather import (
    QUERY_FILLERS,
    WEATHER_MARKERS,
    _field,
    _first_dict,
    _format_weather_answer,
    _looks_like_weather_query,
    _weather_description,
    _weather_location_from_query,
)

__all__ = [
    "AnswerQueryHandler",
    "QUERY_FILLERS",
    "WEATHER_MARKERS",
]
