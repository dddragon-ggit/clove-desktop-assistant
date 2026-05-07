from __future__ import annotations

from typing import Any

from .quality_signatures import action_signature, planner_plan_name, review_signature


def _ordered_unique(values) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _failed_checks_by_case(results: list[dict[str, Any]]) -> dict[str, list[str]]:
    failed_checks: dict[str, list[str]] = {}
    for result in results:
        case_id = str(result["case_id"])
        case_checks = failed_checks.setdefault(case_id, [])
        for code in result.get("failed_quality_checks", []):
            if code not in case_checks:
                case_checks.append(str(code))
    return failed_checks


def build_quality_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    quality_failed = [result for result in results if result.get("quality_ok") is not True]
    runtime_failed = [result for result in results if result.get("ok") is not True]
    fallback_results = [result for result in results if int(result.get("fallback_calls", 0)) > 0]
    categories = sorted({str(result.get("category", "unknown")) for result in results})
    case_ids = _ordered_unique(str(result.get("case_id", "")) for result in results)
    return {
        "total": len(results),
        "case_count": len(case_ids),
        "rounds_per_case": {
            case_id: sum(1 for result in results if result.get("case_id") == case_id)
            for case_id in case_ids
        },
        "quality_passed": sum(1 for result in results if result.get("quality_ok") is True),
        "quality_failed": len(quality_failed),
        "runtime_failed": len(runtime_failed),
        "fallback_calls": sum(int(result.get("fallback_calls", 0)) for result in results),
        "fallback_case_ids": _ordered_unique(str(result["case_id"]) for result in fallback_results),
        "fallback_run_ids": [str(result.get("run_id", result["case_id"])) for result in fallback_results],
        "failed_case_ids": _ordered_unique(str(result["case_id"]) for result in quality_failed),
        "failed_run_ids": [str(result.get("run_id", result["case_id"])) for result in quality_failed],
        "failed_checks": _failed_checks_by_case(quality_failed),
        "categories": {
            category: {
                "total": sum(1 for result in results if result.get("category") == category),
                "passed": sum(
                    1
                    for result in results
                    if result.get("category") == category and result.get("quality_ok") is True
                ),
            }
            for category in categories
        },
    }


def build_stability_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(str(result["case_id"]), []).append(result)

    case_summaries: dict[str, dict[str, Any]] = {}
    unstable_case_ids: list[str] = []
    for case_id, case_results in grouped.items():
        quality_passed = sum(1 for result in case_results if result.get("quality_ok") is True)
        runtime_failed = sum(1 for result in case_results if result.get("ok") is not True)
        fallback_calls = sum(int(result.get("fallback_calls", 0)) for result in case_results)
        action_signatures = _ordered_unique(
            result.get("action_signature") or action_signature(result)
            for result in case_results
        )
        review_signatures = _ordered_unique(
            result.get("review_signature") or review_signature(result)
            for result in case_results
        )
        workflow_statuses = _ordered_unique(
            str(result.get("workflow_status", ""))
            for result in case_results
        )
        plan_names = _ordered_unique(
            result.get("planner_plan_name") or planner_plan_name(result)
            for result in case_results
        )
        failed_checks = _ordered_unique(
            code
            for result in case_results
            for code in result.get("failed_quality_checks", [])
        )

        stable_quality_ok = quality_passed == len(case_results)
        stable_action_signature = len(action_signatures) <= 1
        stable_review_signature = len(review_signatures) <= 1
        stable_workflow_status = len(workflow_statuses) <= 1
        strict_schema_ok = fallback_calls == 0

        instability_reasons: list[str] = []
        if not stable_quality_ok:
            instability_reasons.append("quality_failed")
        if runtime_failed:
            instability_reasons.append("runtime_failed")
        if not stable_action_signature:
            instability_reasons.append("action_signature_changed")
        if not stable_review_signature:
            instability_reasons.append("review_signature_changed")
        if not stable_workflow_status:
            instability_reasons.append("workflow_status_changed")
        if not strict_schema_ok:
            instability_reasons.append("fallback_used")

        stability_ok = not instability_reasons
        if not stability_ok:
            unstable_case_ids.append(case_id)

        case_summaries[case_id] = {
            "category": case_results[0].get("category", "unknown"),
            "runs": len(case_results),
            "passed": quality_passed,
            "failed": len(case_results) - quality_passed,
            "pass_rate": round(quality_passed / len(case_results), 3) if case_results else 0.0,
            "stable_quality_ok": stable_quality_ok,
            "stable_action_signature": stable_action_signature,
            "stable_review_signature": stable_review_signature,
            "stable_workflow_status": stable_workflow_status,
            "strict_schema_ok": strict_schema_ok,
            "stability_ok": stability_ok,
            "instability_reasons": instability_reasons,
            "unique_action_signatures": action_signatures,
            "unique_review_signatures": review_signatures,
            "unique_workflow_statuses": workflow_statuses,
            "unique_plan_names": plan_names,
            "fallback_calls": fallback_calls,
            "failed_checks": failed_checks,
            "failed_run_ids": [
                str(result.get("run_id", result["case_id"]))
                for result in case_results
                if result.get("quality_ok") is not True
            ],
        }

    return {
        "total_runs": len(results),
        "case_count": len(grouped),
        "stable_cases": sum(1 for summary in case_summaries.values() if summary["stability_ok"]),
        "unstable_cases": len(unstable_case_ids),
        "unstable_case_ids": unstable_case_ids,
        "strict_schema_passed": all(
            summary["strict_schema_ok"] for summary in case_summaries.values()
        ),
        "cases": case_summaries,
    }
