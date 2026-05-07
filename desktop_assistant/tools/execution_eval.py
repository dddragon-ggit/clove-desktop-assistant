from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from ..adapters.openai_responses import ProviderResponseError
from .execution_cases import DEFAULT_EXECUTION_CASES, selected_execution_cases
from .execution_models import ExecutionCase
from .execution_runner import run_execution_case, run_suite
from .execution_summary import build_execution_summary
from .execution_verification import (
    _execution_ok,
    _execution_trace_payload,
    _step_verification_ok,
    _verification_ok,
    execution_ok,
    execution_trace_payload,
    step_verification_ok,
    verification_ok,
)
from .quality_models import QualityExpectation

__all__ = [
    "DEFAULT_EXECUTION_CASES",
    "ExecutionCase",
    "QualityExpectation",
    "build_execution_summary",
    "execution_ok",
    "execution_trace_payload",
    "main",
    "parse_args",
    "run_execution_case",
    "run_suite",
    "selected_execution_cases",
    "step_verification_ok",
    "verification_ok",
    "_execution_ok",
    "_execution_trace_payload",
    "_step_verification_ok",
    "_verification_ok",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run real execution evaluations for safe desktop actions."
    )
    parser.add_argument(
        "--ai-backend",
        default="real",
        choices=["real", "fake"],
        help="Use real model adapters or local fake adapters for planning.",
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
        choices=[case.case_id for case in DEFAULT_EXECUTION_CASES],
        help="Run only selected built-in case id. Can be repeated.",
    )
    parser.add_argument(
        "--request",
        action="append",
        default=[],
        help="Add an ad hoc planning-only request. It will not be executed.",
    )
    parser.add_argument(
        "--confirm-execute",
        action="store_true",
        help="Required: acknowledge this tool may open apps, focus windows, or open folders.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON file path to save the execution report.",
    )
    parser.add_argument("--indent", type=int, default=2, help="JSON output indentation.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    if not args.confirm_execute:
        output = {
            "generated_at": datetime.now(UTC).isoformat(),
            "mode": "execution_eval",
            "suite": "desktop_execution",
            "ai_backend": args.ai_backend,
            "executor": "windows",
            "error": {
                "type": "ConfirmationRequired",
                "message": "Pass --confirm-execute to acknowledge this tool may open apps or folders.",
            },
        }
        print(json.dumps(output, ensure_ascii=False, indent=args.indent))
        return 2

    try:
        output = run_suite(args)
        exit_code = 0 if output["summary"]["full_failed"] == 0 else 1
    except (FileNotFoundError, ProviderResponseError, ValidationError, KeyError, ValueError) as exc:
        output = {
            "generated_at": datetime.now(UTC).isoformat(),
            "mode": "execution_eval",
            "suite": "desktop_execution",
            "ai_backend": args.ai_backend,
            "executor": "windows",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
        exit_code = 1

    rendered = json.dumps(output, ensure_ascii=False, indent=args.indent)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
