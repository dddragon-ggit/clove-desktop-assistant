from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SmokeCase:
    case_id: str
    request: str
