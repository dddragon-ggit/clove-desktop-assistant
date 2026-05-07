from __future__ import annotations

import argparse
import unittest

from desktop_assistant.tools.quality_eval import (
    QualityCase,
    QualityExpectation,
    build_quality_summary,
    build_stability_summary,
    evaluate_quality,
    run_suite,
    selected_quality_cases,
)


def _result_with_steps(
    steps: list[dict],
    *,
    workflow_status: str = "dry_run_ready",
    policy_approved: bool = True,
    review_approved: bool = True,
    requires_clarification: bool = False,
) -> dict:
    return {
        "ok": True,
        "case_id": "case",
        "workflow_status": workflow_status,
        "fallback_calls": 0,
        "planner": {
            "requires_clarification": requires_clarification,
            "risk_guess": "low",
            "plan_name": "test",
            "steps": steps,
        },
        "policy": {
            "approved": policy_approved,
            "risk_level": "low",
            "requires_user_confirmation": False,
            "issue_codes": [],
            "issues": [],
        },
        "review": {
            "approved": review_approved,
            "risk_level": "low",
            "needs_user_confirmation": False,
            "summary": "ok",
            "issues": [],
            "rejection_reason": None,
        },
    }


class QualityEvalTests(unittest.TestCase):
    def test_selected_quality_cases_filters_and_appends_custom_requests(self) -> None:
        cases = selected_quality_cases(["weather_xian_today"], ["临时查一下铜价"])

        self.assertEqual([case.case_id for case in cases], ["weather_xian_today", "custom_1"])
        self.assertEqual(cases[1].request, "临时查一下铜价")
        self.assertEqual(cases[1].category, "custom")

    def test_evaluate_quality_passes_expected_answer_query(self) -> None:
        case = QualityCase(
            case_id="weather",
            request="查询今天西安天气",
            category="information_lookup",
            expectation=QualityExpectation(
                expected_action_prefix=("answer_query",),
                forbidden_action_types=("open_url", "show_tasks"),
                required_target_fragments=("西安", "天气"),
                max_steps=1,
                require_policy_approved=True,
                require_review_approved=True,
                require_planner_clarification=False,
            ),
        )
        result = _result_with_steps(
            [
                {
                    "action_type": "answer_query",
                    "target": "查询今天西安天气",
                    "risk_level": "low",
                    "reason": "lookup",
                }
            ]
        )

        checks = evaluate_quality(case, result)

        self.assertTrue(all(check.passed for check in checks))

    def test_evaluate_quality_fails_when_local_app_becomes_url_search(self) -> None:
        case = QualityCase(
            case_id="app",
            request="打开微信应用",
            category="local_app",
            expectation=QualityExpectation(
                expected_action_prefix=("open_app",),
                forbidden_action_types=("open_url",),
                max_steps=1,
            ),
        )
        result = _result_with_steps(
            [
                {
                    "action_type": "open_url",
                    "target": "https://www.baidu.com/s?wd=微信应用",
                    "risk_level": "low",
                    "reason": "search",
                }
            ]
        )

        checks = evaluate_quality(case, result)
        failed_codes = [check.code for check in checks if not check.passed]

        self.assertIn("expected_action_prefix", failed_codes)
        self.assertIn("forbidden_action_type:open_url", failed_codes)

    def test_build_quality_summary_groups_failures(self) -> None:
        summary = build_quality_summary(
            [
                {
                    "case_id": "a",
                    "category": "local_app",
                    "ok": True,
                    "quality_ok": True,
                    "fallback_calls": 0,
                    "failed_quality_checks": [],
                },
                {
                    "case_id": "b",
                    "category": "safety",
                    "ok": True,
                    "quality_ok": False,
                    "fallback_calls": 2,
                    "failed_quality_checks": ["must_be_blocked"],
                },
                {
                    "case_id": "c",
                    "category": "safety",
                    "ok": False,
                    "quality_ok": False,
                    "fallback_calls": 1,
                    "failed_quality_checks": ["runtime_ok"],
                },
            ]
        )

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["quality_passed"], 1)
        self.assertEqual(summary["quality_failed"], 2)
        self.assertEqual(summary["runtime_failed"], 1)
        self.assertEqual(summary["fallback_calls"], 3)
        self.assertEqual(summary["fallback_case_ids"], ["b", "c"])
        self.assertEqual(summary["failed_case_ids"], ["b", "c"])
        self.assertEqual(summary["categories"]["safety"]["total"], 2)

    def test_build_stability_summary_accepts_identical_repeated_runs(self) -> None:
        first = {
            **_result_with_steps(
                [{"action_type": "open_app", "target": "QQ", "risk_level": "low", "reason": "open"}]
            ),
            "case_id": "open_qq",
            "category": "local_app",
            "quality_ok": True,
            "failed_quality_checks": [],
            "round_index": 1,
            "run_id": "open_qq#r1",
        }
        second = {
            **_result_with_steps(
                [{"action_type": "open_app", "target": "QQ", "risk_level": "low", "reason": "open"}]
            ),
            "case_id": "open_qq",
            "category": "local_app",
            "quality_ok": True,
            "failed_quality_checks": [],
            "round_index": 2,
            "run_id": "open_qq#r2",
        }

        summary = build_stability_summary([first, second])

        self.assertEqual(summary["total_runs"], 2)
        self.assertEqual(summary["stable_cases"], 1)
        self.assertEqual(summary["unstable_case_ids"], [])
        self.assertTrue(summary["cases"]["open_qq"]["stability_ok"])

    def test_build_stability_summary_flags_signature_and_fallback_changes(self) -> None:
        first = {
            **_result_with_steps(
                [{"action_type": "open_app", "target": "QQ", "risk_level": "low", "reason": "open"}]
            ),
            "case_id": "open_qq",
            "category": "local_app",
            "quality_ok": True,
            "fallback_calls": 0,
            "failed_quality_checks": [],
            "round_index": 1,
            "run_id": "open_qq#r1",
        }
        second = {
            **_result_with_steps(
                [{"action_type": "open_url", "target": "https://example.com", "risk_level": "low", "reason": "search"}]
            ),
            "case_id": "open_qq",
            "category": "local_app",
            "quality_ok": False,
            "fallback_calls": 1,
            "failed_quality_checks": ["expected_action_prefix"],
            "round_index": 2,
            "run_id": "open_qq#r2",
        }

        summary = build_stability_summary([first, second])
        case_summary = summary["cases"]["open_qq"]

        self.assertEqual(summary["unstable_case_ids"], ["open_qq"])
        self.assertFalse(case_summary["stability_ok"])
        self.assertIn("quality_failed", case_summary["instability_reasons"])
        self.assertIn("action_signature_changed", case_summary["instability_reasons"])
        self.assertIn("fallback_used", case_summary["instability_reasons"])
        self.assertFalse(summary["strict_schema_passed"])

    def test_run_suite_fake_backend_can_pass_targeted_quality_case(self) -> None:
        args = argparse.Namespace(
            ai_backend="fake",
            provider_config_path=None,
            timeout=180.0,
            max_retries=2,
            retry_backoff_seconds=0.0,
            case=["weather_xian_today"],
            request=[],
            output=None,
            indent=2,
        )

        output = run_suite(args)

        self.assertEqual(output["ai_backend"], "fake")
        self.assertEqual(output["summary"]["total"], 1)
        self.assertEqual(output["summary"]["quality_failed"], 0)
        self.assertEqual(output["results"][0]["case_id"], "weather_xian_today")
        self.assertTrue(output["results"][0]["quality_ok"])

    def test_run_suite_fake_backend_supports_multiple_rounds(self) -> None:
        args = argparse.Namespace(
            ai_backend="fake",
            provider_config_path=None,
            timeout=180.0,
            max_retries=2,
            retry_backoff_seconds=0.0,
            case=["weather_xian_today"],
            request=[],
            output=None,
            indent=2,
            rounds=2,
        )

        output = run_suite(args)

        self.assertEqual(output["rounds"], 2)
        self.assertEqual(output["summary"]["total"], 2)
        self.assertEqual(output["summary"]["quality_failed"], 0)
        self.assertEqual(output["stability_summary"]["stable_cases"], 1)
        self.assertEqual(
            [result["round_index"] for result in output["results"]],
            [1, 2],
        )


if __name__ == "__main__":
    unittest.main()
