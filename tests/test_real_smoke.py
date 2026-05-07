from __future__ import annotations

import argparse
import unittest

from desktop_assistant.tools.real_smoke import build_summary, run_suite, selected_cases


class RealSmokeToolTests(unittest.TestCase):
    def test_selected_cases_filters_and_appends_custom_requests(self) -> None:
        cases = selected_cases(["simple_weekly"], ["临时记录一个提醒"])

        self.assertEqual([case.case_id for case in cases], ["simple_weekly", "custom_1"])
        self.assertEqual(cases[1].request, "临时记录一个提醒")

    def test_build_summary_counts_failures_fallbacks_and_rejections(self) -> None:
        summary = build_summary(
            [
                {"case_id": "a", "ok": True, "fallback_calls": 0, "workflow_status": "dry_run_ready"},
                {"case_id": "b", "ok": True, "fallback_calls": 2, "workflow_status": "rejected"},
                {"case_id": "c", "ok": False, "fallback_calls": 1},
            ]
        )

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["fallback_calls"], 3)
        self.assertEqual(summary["fallback_case_ids"], ["b", "c"])
        self.assertEqual(summary["rejected_case_ids"], ["b"])

    def test_run_suite_fake_backend_does_not_need_provider_config(self) -> None:
        args = argparse.Namespace(
            ai_backend="fake",
            provider_config_path=None,
            timeout=180.0,
            max_retries=2,
            retry_backoff_seconds=0.0,
            case=["simple_weekly"],
            request=[],
            indent=2,
        )

        output = run_suite(args)

        self.assertEqual(output["ai_backend"], "fake")
        self.assertIsNone(output["provider_config"])
        self.assertEqual(output["summary"]["total"], 1)
        self.assertEqual(output["summary"]["failed"], 0)
        self.assertEqual(output["summary"]["fallback_calls"], 0)
        self.assertEqual(output["results"][0]["case_id"], "simple_weekly")
        self.assertTrue(output["results"][0]["ok"])
        self.assertEqual(output["results"][0]["workflow_status"], "dry_run_ready")


if __name__ == "__main__":
    unittest.main()
