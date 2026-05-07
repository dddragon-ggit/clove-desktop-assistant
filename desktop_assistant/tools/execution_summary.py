from __future__ import annotations

from typing import Any


def build_execution_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    full_failed = [result for result in results if result.get("full_ok") is not True]
    attempted = [result for result in results if result.get("execution_attempted") is True]
    verification_required = [result for result in results if result.get("verification_required") is True]
    return {
        "total": len(results),
        "planning_passed": sum(1 for result in results if result.get("planning_ok") is True),
        "execution_attempted": len(attempted),
        "execution_passed": sum(1 for result in attempted if result.get("execution_ok") is True),
        "verification_required": len(verification_required),
        "verification_passed": sum(
            1 for result in verification_required if result.get("verification_ok") is True
        ),
        "full_passed": sum(1 for result in results if result.get("full_ok") is True),
        "full_failed": len(full_failed),
        "failed_case_ids": [result["case_id"] for result in full_failed],
        "runtime_failed": sum(1 for result in results if result.get("ok") is not True),
        "fallback_calls": sum(int(result.get("fallback_calls", 0)) for result in results),
    }
