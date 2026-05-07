from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Qt
from PySide6.QtWidgets import QMessageBox, QTableWidgetItem

from ..models import ActionType, RiskLevel
from .execution_feedback import workspace_execution_feedback
from .view_model import (
    WindowStateSummary,
    summarize_window_metadata,
    window_detail_to_plain_text,
    window_row_values,
)
from .workers import WindowActionWorker, WindowListWorker, worker_failure_debug_text


class WindowPanelMixin:
    def _refresh_window_list(self) -> None:
        if not hasattr(self, "window_table"):
            return
        worker = WindowListWorker(limit=50)
        self._start_window_worker(worker, self.on_window_list_finished, "Refreshing windows...")

    def _start_window_worker(self, worker: QObject, finished_slot, status_text: str) -> None:  # noqa: ANN001
        if self.window_busy:
            self.debug_snapshot_text.setPlainText("窗口操作正在进行，请稍等。")
            return
        self._set_window_busy(True)
        self.window_count_label.setText(status_text)
        self.debug_snapshot_text.setPlainText(status_text)
        self.window_thread = QThread()
        self.window_worker = worker
        worker.moveToThread(self.window_thread)
        self.window_thread.started.connect(worker.run)  # type: ignore[attr-defined]
        worker.finished.connect(finished_slot)  # type: ignore[attr-defined]
        worker.failed.connect(self.on_window_worker_failed)  # type: ignore[attr-defined]
        worker.progress.connect(self.set_window_progress)  # type: ignore[attr-defined]
        worker.finished.connect(self.window_thread.quit)  # type: ignore[attr-defined]
        worker.failed.connect(self.window_thread.quit)  # type: ignore[attr-defined]
        worker.finished.connect(worker.deleteLater)  # type: ignore[attr-defined]
        worker.failed.connect(worker.deleteLater)  # type: ignore[attr-defined]
        self.window_thread.finished.connect(self.window_thread.deleteLater)
        self.window_thread.finished.connect(self._finish_window_worker)
        self.window_thread.start()

    def _finish_window_worker(self) -> None:
        self.window_thread = None
        self.window_worker = None
        self._set_window_busy(False)
        if self.refresh_windows_after_action:
            self.refresh_windows_after_action = False
            QTimer.singleShot(250, self._refresh_window_list)

    def _set_window_busy(self, busy: bool) -> None:
        self.window_busy = busy
        if not hasattr(self, "refresh_windows_button"):
            return
        self.refresh_windows_button.setDisabled(busy)
        self._set_window_action_buttons((not busy) and self.selected_window_hwnd is not None)

    def _set_window_action_buttons(self, enabled: bool) -> None:
        for name in [
            "focus_window_button",
            "minimize_window_button",
            "restore_window_button",
            "maximize_window_button",
            "close_window_button",
        ]:
            if hasattr(self, name):
                getattr(self, name).setEnabled(enabled)

    def set_window_progress(self, message: str) -> None:
        self.window_count_label.setText(message)
        self.debug_snapshot_text.setPlainText(message)

    def on_window_worker_failed(self, error: object) -> None:
        self.window_count_label.setText("窗口操作失败")
        self.selected_window_hwnd = None
        self._set_window_action_buttons(False)
        self.debug_snapshot_text.setPlainText(f"窗口操作异常：\n{worker_failure_debug_text(error)}")

    def on_window_list_finished(self, result) -> None:  # noqa: ANN001
        if result.status.value != "success":
            self.window_summaries = []
            self.selected_window_hwnd = None
            self.window_table.setRowCount(0)
            self.window_count_label.setText("窗口不可用")
            self.debug_snapshot_text.setPlainText(self._window_result_to_plain_text(result))
            self._set_window_action_buttons(False)
            return

        self.window_summaries = summarize_window_metadata(result.metadata)
        self.window_count_label.setText(f"可见窗口 {len(self.window_summaries)} 个")
        self._populate_window_table()
        if self.window_summaries:
            selected_row = next(
                (index for index, summary in enumerate(self.window_summaries) if summary.is_foreground),
                0,
            )
            self.window_table.selectRow(selected_row)
            self.load_selected_window_detail()
        else:
            self.selected_window_hwnd = None
            self._set_window_action_buttons(False)
            self.debug_snapshot_text.setPlainText(self._window_result_to_plain_text(result))

    def _populate_window_table(self) -> None:
        self.window_table.setRowCount(len(self.window_summaries))
        for row, summary in enumerate(self.window_summaries):
            for column, value in enumerate(window_row_values(summary)):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, summary.hwnd)
                item.setToolTip(window_detail_to_plain_text(summary))
                self.window_table.setItem(row, column, item)
        self.window_table.resizeRowsToContents()

    def load_selected_window_detail(self) -> None:
        if not hasattr(self, "window_table"):
            return
        summary = self._selected_window_summary()
        if summary is None:
            self.selected_window_hwnd = None
            self._set_window_action_buttons(False)
            return
        self.selected_window_hwnd = summary.hwnd
        self._set_window_action_buttons(not self.window_busy)
        self.debug_snapshot_text.setPlainText(window_detail_to_plain_text(summary))

    def _selected_window_summary(self) -> WindowStateSummary | None:
        row = self.window_table.currentRow()
        if row < 0:
            return None
        item = self.window_table.item(row, 0)
        hwnd = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        try:
            hwnd_int = int(hwnd)
        except (TypeError, ValueError):
            return None
        return next((summary for summary in self.window_summaries if summary.hwnd == hwnd_int), None)

    def _run_window_action(self, action_type: ActionType) -> None:
        summary = self._selected_window_summary()
        if summary is None:
            self.debug_snapshot_text.setPlainText("请先选择一个窗口。")
            return
        if action_type == ActionType.CLOSE_WINDOW:
            reply = QMessageBox.question(
                self,
                "确认关闭",
                f"要请求关闭这个窗口吗？\n\n{summary.title or summary.hwnd}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.debug_snapshot_text.setPlainText("已取消关闭窗口。")
                return
        risk = RiskLevel.MEDIUM if action_type == ActionType.CLOSE_WINDOW else RiskLevel.LOW
        worker = WindowActionWorker(
            action_type=action_type,
            target=f"hwnd:{summary.hwnd}",
            params={"hwnd": summary.hwnd},
            risk_level=risk,
        )
        self._start_window_worker(worker, self.on_window_action_finished, f"Running {action_type.value}...")

    def on_window_action_finished(self, result) -> None:  # noqa: ANN001
        self.debug_snapshot_text.setPlainText(self._window_result_to_plain_text(result))
        if result.status.value == "success":
            self.summary_label.setText(result.message)
            self.window_count_label.setText("窗口操作成功")
            self.refresh_windows_after_action = True
        else:
            self.window_count_label.setText("窗口操作失败")

    @staticmethod
    def _window_result_to_plain_text(result) -> str:  # noqa: ANN001
        if result.action.action_type == ActionType.LIST_WINDOWS and result.status.value == "success":
            summaries = summarize_window_metadata(result.metadata)
            lines = ["窗口列表已刷新。", f"可见窗口：{len(summaries)} 个"]
            foreground = next((item for item in summaries if item.is_foreground), None)
            if foreground is not None:
                lines.append(f"当前前台：{foreground.title or foreground.executable_path or foreground.hwnd}")
            return "\n".join(lines)
        return workspace_execution_feedback([result])
