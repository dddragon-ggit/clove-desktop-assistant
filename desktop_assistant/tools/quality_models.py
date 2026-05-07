from __future__ import annotations

from dataclasses import dataclass

from .smoke_models import SmokeCase


@dataclass(frozen=True)
class QualityExpectation:
    allowed_workflow_statuses: tuple[str, ...] = ("dry_run_ready",)
    expected_action_prefix: tuple[str, ...] = ()
    required_action_types: tuple[str, ...] = ()
    forbidden_action_types: tuple[str, ...] = ()
    required_target_fragments: tuple[str, ...] = ()
    forbidden_target_fragments: tuple[str, ...] = ()
    min_steps: int | None = None
    max_steps: int | None = None
    require_policy_approved: bool | None = None
    require_review_approved: bool | None = None
    require_planner_clarification: bool | None = None
    must_be_blocked: bool = False


@dataclass(frozen=True)
class QualityCase:
    case_id: str
    request: str
    category: str
    expectation: QualityExpectation
    notes: str = ""

    def to_smoke_case(self) -> SmokeCase:
        return SmokeCase(case_id=self.case_id, request=self.request)


@dataclass(frozen=True)
class QualityCheck:
    code: str
    passed: bool
    message: str
