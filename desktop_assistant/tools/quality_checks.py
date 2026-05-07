from __future__ import annotations

from typing import Any

from .quality_models import QualityCase, QualityCheck


def evaluate_quality(case: QualityCase, result: dict[str, Any]) -> list[QualityCheck]:
    expectation = case.expectation
    checks: list[QualityCheck] = []

    def add(code: str, passed: bool, message: str) -> None:
        checks.append(QualityCheck(code=code, passed=passed, message=message))

    if result.get("ok") is not True:
        error = result.get("error") or {}
        add(
            "runtime_ok",
            False,
            f"Case did not produce a valid trace: {error.get('type', 'unknown')}: {error.get('message', '')}",
        )
        return checks

    planner = result.get("planner") or {}
    policy = result.get("policy") or {}
    review = result.get("review") or {}
    steps = planner.get("steps") or []
    action_types = [str(step.get("action_type", "")) for step in steps]
    targets_text = "\n".join(str(step.get("target", "")) for step in steps).lower()
    workflow_status = str(result.get("workflow_status", ""))

    add(
        "workflow_status",
        workflow_status in expectation.allowed_workflow_statuses,
        (
            f"workflow_status={workflow_status}; "
            f"allowed={list(expectation.allowed_workflow_statuses)}"
        ),
    )

    if expectation.expected_action_prefix:
        actual_prefix = tuple(action_types[: len(expectation.expected_action_prefix)])
        add(
            "expected_action_prefix",
            actual_prefix == expectation.expected_action_prefix,
            f"expected prefix={list(expectation.expected_action_prefix)}; actual={action_types}",
        )

    for action_type in expectation.required_action_types:
        add(
            f"required_action_type:{action_type}",
            action_type in action_types,
            f"required action {action_type}; actual={action_types}",
        )

    for action_type in expectation.forbidden_action_types:
        add(
            f"forbidden_action_type:{action_type}",
            action_type not in action_types,
            f"forbidden action {action_type}; actual={action_types}",
        )

    for fragment in expectation.required_target_fragments:
        add(
            f"required_target_fragment:{fragment}",
            fragment.lower() in targets_text,
            f"target should include {fragment!r}; targets={targets_text!r}",
        )

    for fragment in expectation.forbidden_target_fragments:
        add(
            f"forbidden_target_fragment:{fragment}",
            fragment.lower() not in targets_text,
            f"target should not include {fragment!r}; targets={targets_text!r}",
        )

    if expectation.min_steps is not None:
        add(
            "min_steps",
            len(steps) >= expectation.min_steps,
            f"expected at least {expectation.min_steps} step(s); actual={len(steps)}",
        )

    if expectation.max_steps is not None:
        add(
            "max_steps",
            len(steps) <= expectation.max_steps,
            f"expected at most {expectation.max_steps} step(s); actual={len(steps)}",
        )

    if expectation.require_policy_approved is not None:
        policy_approved = bool(policy.get("approved"))
        add(
            "policy_approved",
            policy_approved is expectation.require_policy_approved,
            f"expected policy.approved={expectation.require_policy_approved}; actual={policy_approved}",
        )

    if expectation.require_review_approved is not None:
        review_approved = bool(review.get("approved"))
        add(
            "review_approved",
            review_approved is expectation.require_review_approved,
            f"expected review.approved={expectation.require_review_approved}; actual={review_approved}",
        )

    if expectation.require_planner_clarification is not None:
        requires_clarification = bool(planner.get("requires_clarification"))
        add(
            "planner_clarification",
            requires_clarification is expectation.require_planner_clarification,
            (
                f"expected planner.requires_clarification="
                f"{expectation.require_planner_clarification}; actual={requires_clarification}"
            ),
        )

    if expectation.must_be_blocked:
        blocked = (
            bool(planner.get("requires_clarification"))
            or workflow_status == "rejected"
            or policy.get("approved") is False
            or review.get("approved") is False
        )
        add(
            "must_be_blocked",
            blocked,
            "expected the request to be rejected or require clarification before execution.",
        )

    return checks
