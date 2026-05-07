from __future__ import annotations

import argparse
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from ..adapters.openai_responses import ProviderResponseError
from ..core.orchestrator import WorkflowOrchestrator
from ..models import RunMode, WorkflowRequest
from .smoke_cases import selected_cases
from .smoke_client import CountingOpenAIResponsesClient
from .smoke_models import SmokeCase
from .smoke_orchestrator import build_smoke_orchestrator
from .smoke_summary import build_summary


def run_smoke_case(
    orchestrator: WorkflowOrchestrator,
    case: SmokeCase,
    client: CountingOpenAIResponsesClient | None,
) -> dict[str, Any]:
    fallback_before = client.fallback_count if client is not None else 0
    result: dict[str, Any] = {
        "case_id": case.case_id,
        "request": case.request,
    }

    try:
        trace = orchestrator.run(WorkflowRequest(user_request=case.request, run_mode=RunMode.DRY_RUN))
        fallback_calls = (client.fallback_count - fallback_before) if client is not None else 0
        steps = trace.planner_result.action_plan.steps
        result.update(
            {
                "ok": True,
                "trace_id": trace.trace_id,
                "workflow_status": trace.status.value,
                "fallback_calls": fallback_calls,
                "planner": {
                    "requires_clarification": trace.planner_result.requires_clarification,
                    "risk_guess": trace.planner_result.risk_guess.value,
                    "plan_name": trace.planner_result.action_plan.plan_name,
                    "steps": [
                        {
                            "action_type": step.action_type.value,
                            "target": step.target,
                            "risk_level": step.risk_level.value,
                            "reason": step.reason,
                        }
                        for step in steps
                    ],
                },
                "policy": {
                    "approved": trace.policy_decision.approved,
                    "risk_level": trace.policy_decision.risk_level.value,
                    "requires_user_confirmation": trace.policy_decision.requires_user_confirmation,
                    "issue_codes": [issue.code for issue in trace.policy_decision.issues],
                    "issues": [issue.message for issue in trace.policy_decision.issues],
                },
                "review": {
                    "approved": trace.review_result.approved,
                    "risk_level": trace.review_result.risk_level.value,
                    "needs_user_confirmation": trace.review_result.needs_user_confirmation,
                    "summary": trace.review_result.review_summary,
                    "issues": trace.review_result.issues,
                    "rejection_reason": trace.review_result.rejection_reason,
                },
            }
        )
    except (ProviderResponseError, ValidationError, KeyError, ValueError) as exc:
        fallback_calls = (client.fallback_count - fallback_before) if client is not None else 0
        result.update(
            {
                "ok": False,
                "fallback_calls": fallback_calls,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }
        )

    return result


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    cases = selected_cases(args.case, args.request)
    orchestrator, provider_info, client = build_smoke_orchestrator(
        ai_backend=args.ai_backend,
        provider_config_path=args.provider_config_path,
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
    )
    results = [run_smoke_case(orchestrator, case, client) for case in cases]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "dry_run",
        "ai_backend": args.ai_backend,
        "executor": "fake",
        "provider_config": provider_info,
        "summary": build_summary(results),
        "results": results,
    }
