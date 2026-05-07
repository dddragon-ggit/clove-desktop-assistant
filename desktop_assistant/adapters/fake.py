from __future__ import annotations

from .fake_context import FakeContextProvider
from .fake_executor import FakeExecutor
from .fake_planner import FakePlanner, _refined_fake_plan
from .fake_planner_rules import (
    _APP_MARKERS,
    _FOCUS_MARKERS,
    _KNOWN_WEBSITE_URLS,
    _LEADING_TARGET_FILLERS,
    _LOOKUP_MARKERS,
    _OPEN_WEB_MARKERS,
    _PROJECT_MARKERS,
    _URL_PATTERN,
    _WINDOW_ACTION_MARKERS,
    _WINDOW_LIST_MARKERS,
    _clean_app_target,
    _clean_open_target,
    _clean_window_target,
    _extract_open_target,
    _extract_url,
    _looks_unsafe_request,
    _requested_app_target,
    _requested_focus_target,
    _requested_lookup_query,
    _requested_project_target,
    _requested_replacement_target,
    _requested_website_url,
    _requested_window_action,
)
from .fake_reviewer import FakeReviewer

__all__ = [
    "FakeContextProvider",
    "FakeExecutor",
    "FakePlanner",
    "FakeReviewer",
]
