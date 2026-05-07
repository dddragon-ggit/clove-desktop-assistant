from __future__ import annotations

import unittest

from desktop_assistant.capability.executor import execution_success
from desktop_assistant.models import ActionStep, ActionType
from desktop_assistant.ui.view_model import WindowStateSummary, window_detail_to_plain_text, window_state_label
from desktop_assistant.ui.window_panel import WindowPanelMixin


class WindowFeedbackTests(unittest.TestCase):
    def test_window_detail_uses_product_language(self) -> None:
        summary = WindowStateSummary(
            hwnd=123,
            title="Cursor",
            process_id=456,
            executable_path=r"C:\Apps\Cursor.exe",
            is_foreground=True,
        )

        self.assertEqual(window_state_label(summary), "前台，普通")
        detail = window_detail_to_plain_text(summary)
        self.assertIn("窗口：Cursor", detail)
        self.assertIn("程序位置：", detail)

    def test_list_windows_result_summarizes_visible_count(self) -> None:
        result = execution_success(
            ActionStep(action_type=ActionType.LIST_WINDOWS, target="visible"),
            0,
            "ok",
            metadata={
                "windows": [{"hwnd": 1, "title": "Cursor", "process_id": 10}],
                "foreground_window": {"hwnd": 1},
            },
        )

        text = WindowPanelMixin._window_result_to_plain_text(result)

        self.assertIn("窗口列表已刷新", text)
        self.assertIn("可见窗口：1 个", text)
        self.assertIn("当前前台：Cursor", text)


if __name__ == "__main__":
    unittest.main()
