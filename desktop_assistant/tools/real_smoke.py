from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

from pydantic import ValidationError

from ..adapters.openai_responses import ProviderResponseError
from .smoke_cases import DEFAULT_CASES, selected_cases
from .smoke_client import CountingOpenAIResponsesClient
from .smoke_models import SmokeCase
from .smoke_orchestrator import build_smoke_orchestrator
from .smoke_runner import run_smoke_case, run_suite
from .smoke_summary import build_summary

__all__ = [
    "DEFAULT_CASES",
    "CountingOpenAIResponsesClient",
    "SmokeCase",
    "build_smoke_orchestrator",
    "build_summary",
    "main",
    "parse_args",
    "run_smoke_case",
    "run_suite",
    "selected_cases",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real Planner/Reviewer smoke checks without executing desktop actions."
    )
    parser.add_argument(
        "--ai-backend",
        default="real",
        choices=["real", "fake"],
        help="Use real model adapters or local fake adapters.",
    )
    parser.add_argument(
        "--provider-config-path",
        default=None,
        help="Optional provider config JSON path. Environment variables still take priority.",
    )
    parser.add_argument("--timeout", type=float, default=180.0, help="HTTP timeout for real model calls.")
    parser.add_argument("--max-retries", type=int, default=2, help="Retries for retryable provider failures.")
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=0.5,
        help="Initial exponential backoff delay between provider retries.",
    )
    parser.add_argument(
        "--case",
        action="append",
        choices=[case.case_id for case in DEFAULT_CASES],
        help="Run only selected built-in case id. Can be repeated.",
    )
    parser.add_argument(
        "--request",
        action="append",
        default=[],
        help="Add an ad hoc request to the smoke suite. Can be repeated.",
    )
    parser.add_argument("--indent", type=int, default=2, help="JSON output indentation.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    try:
        output = run_suite(args)
        exit_code = 0 if output["summary"]["failed"] == 0 else 1
    except (FileNotFoundError, ProviderResponseError, ValidationError, KeyError, ValueError) as exc:
        output = {
            "generated_at": datetime.now(UTC).isoformat(),
            "mode": "dry_run",
            "ai_backend": args.ai_backend,
            "executor": "fake",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
        exit_code = 1

    print(json.dumps(output, ensure_ascii=False, indent=args.indent))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
