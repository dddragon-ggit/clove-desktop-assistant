from __future__ import annotations

from typing import Any


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(results),
        "passed": sum(1 for result in results if result.get("ok") is True),
        "failed": sum(1 for result in results if result.get("ok") is not True),
        "fallback_calls": sum(int(result.get("fallback_calls", 0)) for result in results),
        "fallback_case_ids": [
            result["case_id"]
            for result in results
            if int(result.get("fallback_calls", 0)) > 0
        ],
        "rejected_case_ids": [
            result["case_id"]
            for result in results
            if result.get("workflow_status") == "rejected"
        ],
    }
