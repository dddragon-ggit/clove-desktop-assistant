from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from .quality_cases import selected_quality_cases
from .quality_checks import evaluate_quality
from .quality_models import QualityCase
from .quality_signatures import action_signature, build_run_id, planner_plan_name, review_signature
from .quality_summary import build_quality_summary, build_stability_summary
from .smoke_client import CountingOpenAIResponsesClient
from .smoke_orchestrator import build_smoke_orchestrator
from .smoke_runner import run_smoke_case


def run_quality_case(
    orchestrator,
    case: QualityCase,
    client: CountingOpenAIResponsesClient | None,
    *,
    round_index: int = 1,
) -> dict[str, Any]:
    smoke_result = run_smoke_case(orchestrator, case.to_smoke_case(), client)
    checks = evaluate_quality(case, smoke_result)
    quality_ok = bool(smoke_result.get("ok")) and all(check.passed for check in checks)
    result = {
        **smoke_result,
        "round_index": round_index,
        "run_id": build_run_id(case.case_id, round_index),
        "category": case.category,
        "quality_ok": quality_ok,
        "notes": case.notes,
        "expectation": asdict(case.expectation),
        "quality_checks": [asdict(check) for check in checks],
        "failed_quality_checks": [check.code for check in checks if not check.passed],
    }
    result["planner_plan_name"] = planner_plan_name(result)
    result["action_signature"] = action_signature(result)
    result["review_signature"] = review_signature(result)
    return result


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    cases = selected_quality_cases(args.case, args.request)
    rounds = max(1, int(getattr(args, "rounds", 1) or 1))
    orchestrator, provider_info, client = build_smoke_orchestrator(
        ai_backend=args.ai_backend,
        provider_config_path=args.provider_config_path,
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
    )
    results = [
        run_quality_case(orchestrator, case, client, round_index=round_index)
        for round_index in range(1, rounds + 1)
        for case in cases
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "dry_run",
        "suite": "planner_reviewer_quality",
        "rounds": rounds,
        "ai_backend": args.ai_backend,
        "executor": "fake",
        "provider_config": provider_info,
        "summary": build_quality_summary(results),
        "stability_summary": build_stability_summary(results),
        "results": results,
    }
