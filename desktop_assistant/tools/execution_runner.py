from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Callable

from ..adapters.windows_executor import WindowsExecutor
from .execution_cases import selected_execution_cases
from .execution_models import ExecutionCase
from .execution_summary import build_execution_summary
from .execution_verification import execution_ok, execution_trace_payload, verification_ok
from .quality_checks import evaluate_quality
from .smoke_client import CountingOpenAIResponsesClient
from .smoke_orchestrator import build_smoke_orchestrator
from .smoke_runner import run_smoke_case


def run_execution_case(
    orchestrator,
    case: ExecutionCase,
    client: CountingOpenAIResponsesClient | None,
    *,
    executor_factory: Callable[[], Any] = WindowsExecutor,
) -> dict[str, Any]:
    smoke_result = run_smoke_case(orchestrator, case.to_smoke_case(), client)
    quality_checks = evaluate_quality(case.to_quality_case(), smoke_result)
    planning_ok = bool(smoke_result.get("ok")) and all(check.passed for check in quality_checks)

    result: dict[str, Any] = {
        **smoke_result,
        "category": case.category,
        "notes": case.notes,
        "planning_ok": planning_ok,
        "planning_checks": [asdict(check) for check in quality_checks],
        "failed_planning_checks": [check.code for check in quality_checks if not check.passed],
        "execution_attempted": False,
        "execution_ok": None,
        "verification_required": bool(case.verification_action_types),
        "verification_ok": None,
        "full_ok": False,
        "execution_trace": None,
    }

    if not planning_ok:
        result["execution_skip_reason"] = "planning_failed"
        return result
    if not case.allow_execution:
        result["execution_skip_reason"] = "case_is_planning_only"
        result["full_ok"] = True
        return result

    trace_id = str(smoke_result["trace_id"])
    orchestrator.executor = executor_factory()
    orchestrator.max_recovery_attempts_per_trace = 0
    trace = orchestrator.execute_all(trace_id)
    trace_execution_ok = execution_ok(trace)
    trace_verification_ok = verification_ok(trace, case.verification_action_types)

    result.update(
        {
            "execution_attempted": True,
            "execution_ok": trace_execution_ok,
            "verification_ok": trace_verification_ok,
            "full_ok": trace_execution_ok and (trace_verification_ok is not False),
            "execution_trace": execution_trace_payload(trace),
        }
    )
    return result


def run_suite(
    args: argparse.Namespace,
    *,
    executor_factory: Callable[[], Any] = WindowsExecutor,
) -> dict[str, Any]:
    cases = selected_execution_cases(args.case, args.request)
    orchestrator, provider_info, client = build_smoke_orchestrator(
        ai_backend=args.ai_backend,
        provider_config_path=args.provider_config_path,
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
    )
    results = [
        run_execution_case(orchestrator, case, client, executor_factory=executor_factory)
        for case in cases
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "execution_eval",
        "suite": "desktop_execution",
        "ai_backend": args.ai_backend,
        "executor": "windows",
        "provider_config": provider_info,
        "summary": build_execution_summary(results),
        "results": results,
    }
