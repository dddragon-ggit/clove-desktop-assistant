from __future__ import annotations

from typing import Any


def build_run_id(case_id: str, round_index: int) -> str:
    return f"{case_id}#r{round_index}"


def planner_plan_name(result: dict[str, Any]) -> str:
    planner = result.get("planner") or {}
    return str(planner.get("plan_name", ""))


def action_signature(result: dict[str, Any]) -> str:
    if result.get("ok") is not True:
        error = result.get("error") or {}
        return f"runtime_error:{error.get('type', 'unknown')}"

    planner = result.get("planner") or {}
    steps = planner.get("steps") or []
    if not steps:
        return "(no_steps)"

    parts: list[str] = []
    for step in steps:
        action_type = str(step.get("action_type", ""))
        target = " ".join(str(step.get("target", "")).split())
        parts.append(f"{action_type}:{target}")
    return " | ".join(parts)


def review_signature(result: dict[str, Any]) -> str:
    if result.get("ok") is not True:
        error = result.get("error") or {}
        return f"runtime_error:{error.get('type', 'unknown')}"

    planner = result.get("planner") or {}
    policy = result.get("policy") or {}
    review = result.get("review") or {}
    return ";".join(
        [
            f"planner_clarification={bool(planner.get('requires_clarification'))}",
            f"policy={bool(policy.get('approved'))}:{policy.get('risk_level')}:{bool(policy.get('requires_user_confirmation'))}",
            f"review={bool(review.get('approved'))}:{review.get('risk_level')}:{bool(review.get('needs_user_confirmation'))}",
        ]
    )
