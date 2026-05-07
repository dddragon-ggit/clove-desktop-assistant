from __future__ import annotations

from dataclasses import dataclass

from .quality_models import QualityCase, QualityExpectation
from .smoke_models import SmokeCase


@dataclass(frozen=True)
class ExecutionCase:
    case_id: str
    request: str
    category: str
    quality_expectation: QualityExpectation
    verification_action_types: tuple[str, ...] = ()
    allow_execution: bool = True
    notes: str = ""

    def to_smoke_case(self) -> SmokeCase:
        return SmokeCase(case_id=self.case_id, request=self.request)

    def to_quality_case(self) -> QualityCase:
        return QualityCase(
            case_id=self.case_id,
            request=self.request,
            category=self.category,
            expectation=self.quality_expectation,
            notes=self.notes,
        )
