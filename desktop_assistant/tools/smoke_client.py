from __future__ import annotations

from typing import Any

from ..adapters.openai_responses import OpenAIResponsesClient


class CountingOpenAIResponsesClient(OpenAIResponsesClient):
    """Responses client that exposes fallback count for smoke diagnostics."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fallback_count = 0

    def _fallback_json_prompt(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.fallback_count += 1
        return super()._fallback_json_prompt(*args, **kwargs)
