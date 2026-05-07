from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from ..adapters.openai_responses import ProviderResponseError
from .quality_cases import DEFAULT_QUALITY_CASES, selected_quality_cases
from .quality_checks import evaluate_quality
from .quality_models import QualityCase, QualityCheck, QualityExpectation
from .quality_runner import run_quality_case, run_suite
from .quality_signatures import action_signature, build_run_id, planner_plan_name, review_signature
from .quality_summary import build_quality_summary, build_stability_summary

__all__ = [
    "DEFAULT_QUALITY_CASES",
    "QualityCase",
    "QualityCheck",
    "QualityExpectation",
    "action_signature",
    "build_quality_summary",
    "build_run_id",
    "build_stability_summary",
    "evaluate_quality",
    "main",
    "parse_args",
    "planner_plan_name",
    "review_signature",
    "run_quality_case",
    "run_suite",
    "selected_quality_cases",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Planner/Reviewer quality evaluations without executing desktop actions."
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
        choices=[case.case_id for case in DEFAULT_QUALITY_CASES],
        help="Run only selected built-in case id. Can be repeated.",
    )
    parser.add_argument(
        "--request",
        action="append",
        default=[],
        help="Add an ad hoc request with structural checks only. Can be repeated.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="Run each selected case this many times to evaluate output stability.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON file path to save the evaluation report.",
    )
    parser.add_argument("--indent", type=int, default=2, help="JSON output indentation.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    try:
        output = run_suite(args)
        exit_code = (
            0
            if output["summary"]["quality_failed"] == 0
            and output["stability_summary"]["unstable_cases"] == 0
            else 1
        )
    except (FileNotFoundError, ProviderResponseError, ValidationError, KeyError, ValueError) as exc:
        output = {
            "generated_at": datetime.now(UTC).isoformat(),
            "mode": "dry_run",
            "suite": "planner_reviewer_quality",
            "ai_backend": args.ai_backend,
            "executor": "fake",
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
