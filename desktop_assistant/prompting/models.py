from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderedPrompt:
    template_id: str
    system_prompt: str
