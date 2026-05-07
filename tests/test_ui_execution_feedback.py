from __future__ import annotations

import unittest

from desktop_assistant.capability.executor import execution_failed, execution_success
from desktop_assistant.models import ActionStep, ActionType
from desktop_assistant.ui.execution_feedback import workspace_execution_feedback
from desktop_assistant.ui.execution_remedies import remedies_for_results


class ExecutionFeedbackTests(unittest.TestCase):
    def test_success_feedback_is_product_language(self) -> None:
        result = execution_success(
            ActionStep(action_type=ActionType.OPEN_URL, target="https://example.com"),
            0,
            "[trace-1] Opened URL: https://example.com",
        )

        text = workspace_execution_feedback([result])

        self.assertIn("执行完成", text)
        self.assertIn("已打开网页：https://example.com", text)
        self.assertNotIn("open_url ->", text)

    def test_partial_feedback_explains_app_running_without_window(self) -> None:
        success = execution_success(
            ActionStep(action_type=ActionType.OPEN_URL, target="https://example.com"),
            0,
            "[trace-1] Opened URL: https://example.com",
        )
        failed = execution_failed(
            ActionStep(action_type=ActionType.OPEN_APP, target="QQ"),
            1,
            "[trace-1] App process is running but no visible window was detected: QQ",
            code="APP_PROCESS_RUNNING_NO_WINDOW",
            details={"app_name": "QQ"},
            remedy="The app appears to be running in the background.",
        )

        text = workspace_execution_feedback([success, failed])

        self.assertIn("部分完成", text)
        self.assertIn("QQ", text)
        self.assertIn("进程已经在运行", text)
        self.assertIn("原因代码：APP_PROCESS_RUNNING_NO_WINDOW", text)
        self.assertNotIn("open_app ->", text)

    def test_failed_feedback_keeps_diagnosis_code_and_clear_remedy(self) -> None:
        result = execution_failed(
            ActionStep(action_type=ActionType.OPEN_APP, target="Battle.net"),
            0,
            "[trace-1] App is not in inventory: Battle.net",
            code="APP_NOT_IN_INVENTORY",
            details={"target": "Battle.net"},
            remedy="Refresh app_inventory.json or check whether the app is installed.",
        )

        text = workspace_execution_feedback([result])

        self.assertIn("没有完成", text)
        self.assertIn("没有在应用清单里找到「Battle.net」", text)
        self.assertIn("可以刷新应用清单", text)
        self.assertIn("可以继续：", text)
        self.assertIn("刷新应用清单", text)
        self.assertIn("原因代码：APP_NOT_IN_INVENTORY", text)
        self.assertNotIn("open_app ->", text)

    def test_query_success_feedback_shows_answer_sources_and_confidence(self) -> None:
        result = execution_success(
            ActionStep(action_type=ActionType.ANSWER_QUERY, target="查询今天黄金价格"),
            0,
            "[trace-1] Answer for 查询今天黄金价格",
            metadata={
                "answer": "现货黄金约 2300 美元/盎司。",
                "confidence": "low",
                "confidence_reason": "网页摘要片段，需要点开来源确认。",
                "verification_status": "single_snippet_source",
                "source_summary": "已从 1 个来源提取结果，建议需要精确结论时点开来源核对。",
                "sources": ["https://example.com/gold"],
                "fallback_url": "https://www.baidu.com/s?wd=gold",
            },
        )

        text = workspace_execution_feedback([result])

        self.assertIn("查询结果：现货黄金约 2300 美元/盎司。", text)
        self.assertIn("可信度：低", text)
        self.assertIn("验证状态：单一网页摘要", text)
        self.assertIn("来源概况：已从 1 个来源", text)
        self.assertIn("https://example.com/gold", text)
        self.assertIn("兜底搜索", text)

    def test_window_success_feedback_shows_verified_state(self) -> None:
        result = execution_success(
            ActionStep(action_type=ActionType.MINIMIZE_WINDOW, target="QQ"),
            0,
            "[trace-1] Minimized window: QQ",
            metadata={
                "verification_status": "minimized_confirmed",
                "verified_window": {"title": "QQ", "is_minimized": True, "is_maximized": False},
            },
        )

        text = workspace_execution_feedback([result])

        self.assertIn("状态确认：已确认窗口最小化", text)
        self.assertIn("窗口状态：QQ（已最小化）", text)

    def test_remedy_generation_supports_focus_retry_and_query_fallback(self) -> None:
        app_result = execution_failed(
            ActionStep(action_type=ActionType.OPEN_APP, target="QQ"),
            0,
            "no window",
            code="APP_PROCESS_RUNNING_NO_WINDOW",
            details={"app_name": "QQ"},
        )
        query_result = execution_failed(
            ActionStep(action_type=ActionType.ANSWER_QUERY, target="查询铜价"),
            1,
            "no answer",
            code="WEB_QUERY_NO_DIRECT_ANSWER",
            details={"fallback_url": "https://www.baidu.com/s?wd=%E9%93%9C%E4%BB%B7"},
        )

        remedies = remedies_for_results([app_result, query_result])

        self.assertEqual(remedies[0].kind, "retry_focus_app")
        self.assertEqual(remedies[0].target, "QQ")
        self.assertEqual(remedies[0].delay_seconds, 5)
        self.assertEqual(remedies[1].kind, "open_fallback_url")


if __name__ == "__main__":
    unittest.main()
