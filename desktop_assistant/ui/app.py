from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QPoint, QThread, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QListWidgetItem,
    QMainWindow,
    QVBoxLayout,
)

from ..action_trust import TrustedActionRule
from ..projects import ProjectCatalogStore, ProjectLocation
from ..recipe import (
    RecipeStore,
    WorkflowRecipe,
)
from ..storage.recovery_events import RecoveryEventStore
from ..storage.sqlite import SQLiteStorage
from .capability_panel import CapabilityPanelMixin
from .main_window_interactions import MainWindowInteractionMixin
from .main_window_layout import MainWindowLayoutMixin
from .project_panel import ProjectPanelMixin
from .recipe_panel import RecipePanelMixin
from .view_model import (
    CapabilitySummary,
    DebugRunSummary,
    RecentTraceSummary,
    RecoveryEventSummary,
    WindowStateSummary,
    WorkflowSummary,
    debug_run_label,
    recent_trace_label,
    recovery_event_detail_text,
    recovery_event_label,
    summarize_debug_run,
    summarize_recent_trace,
    summarize_recovery_event,
    summarize_trace,
)
from .styles import ASSISTANT_STYLES
from .trust_panel import TrustPanelMixin
from .window_panel import WindowPanelMixin


class FloatingAssistantWindow(
    MainWindowLayoutMixin,
    MainWindowInteractionMixin,
    WindowPanelMixin,
    TrustPanelMixin,
    ProjectPanelMixin,
    RecipePanelMixin,
    CapabilityPanelMixin,
    QMainWindow,
):
    def __init__(self) -> None:
        super().__init__()
        self.worker_thread: QThread | None = None
        self.window_thread: QThread | None = None
        self.drag_position: QPoint | None = None
        self.is_compact = False
        self.latest_summary: WorkflowSummary | None = None
        self.storage = SQLiteStorage()
        self.app_inventory_error: str | None = None
        self.app_inventory_count = 0
        self.capability_catalog_error: str | None = None
        self.enabled_capability_count = 0
        self.capability_catalog_path = ""
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(1000)
        self.progress_timer.timeout.connect(self._tick_running)
        self.running_seconds = 0
        self.active_operation = ""
        self.recent_records: dict[str, RecentTraceSummary] = {}
        self.debug_records: dict[str, DebugRunSummary] = {}
        self.recovery_event_store = RecoveryEventStore()
        self.recovery_records: dict[str, RecoveryEventSummary] = {}
        self.capability_records: dict[str, CapabilitySummary] = {}
        self.capability_summaries: list[CapabilitySummary] = []
        self.selected_capability_action: str | None = None
        self.window_summaries: list[WindowStateSummary] = []
        self.selected_window_hwnd: int | None = None
        self.window_busy = False
        self.window_worker: QObject | None = None
        self.refresh_windows_after_action = False
        self.recipe_store = RecipeStore()
        self.project_store = ProjectCatalogStore()
        self.recipe_records: dict[str, WorkflowRecipe] = {}
        self.project_records: dict[str, ProjectLocation] = {}
        self.trust_records: dict[str, TrustedActionRule] = {}
        self.selected_recipe_id: str | None = None
        self.selected_project_name: str | None = None
        self.selected_trust_key: str | None = None
        self.active_recipe_id: str | None = None
        self.active_draft_goal: str | None = None
        self.active_draft_refinements: list[str] = []
        self.expanded_height = 840
        self._ensure_app_inventory_cache()
        self._ensure_capability_catalog()

        self.setWindowTitle("Desktop Assistant")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(560, 520)
        self.resize(720, self.expanded_height)

        self.root = QFrame()
        self.root.setObjectName("assistantRoot")
        self.setCentralWidget(self.root)

        root_layout = QVBoxLayout(self.root)
        root_layout.setContentsMargins(18, 16, 18, 18)
        root_layout.setSpacing(12)

        self._build_header(root_layout)
        self._build_status(root_layout)
        self._build_input(root_layout)
        self._build_result_area(root_layout)
        self._refresh_recent_traces()
        self._refresh_recovery_events()
        self._apply_styles()
        self._move_to_bottom_right()

    def _refresh_recent_traces(self) -> None:
        self.recent_list.clear()
        self.recent_records.clear()
        try:
            records = self.storage.list_recent_traces(limit=8)
        except (KeyError, ValueError):
            return

        for record in records:
            summary = summarize_recent_trace(record)
            self.recent_records[summary.trace_id] = summary
            item = QListWidgetItem(recent_trace_label(summary))
            item.setData(Qt.ItemDataRole.UserRole, summary.trace_id)
            item.setToolTip(f"{summary.updated_at}\n{summary.request}\n{summary.trace_id}")
            self.recent_list.addItem(item)

    def load_recent_trace(self, item: QListWidgetItem) -> None:
        trace_id = item.data(Qt.ItemDataRole.UserRole)
        if not trace_id:
            return
        try:
            trace = self.storage.get_trace(str(trace_id))
        except KeyError as exc:
            self.set_error(str(exc))
            return
        summary = summarize_trace(trace)
        self.on_dry_run_finished(summary)
        self.summary_label.setText(f"Loaded trace {summary.trace_id[:8]} from SQLite.")
        self._refresh_debug_runs(summary.trace_id)

    def _clear_debug_runs(self, label: str) -> None:
        self.debug_list.clear()
        self.debug_records.clear()
        self.debug_count_label.setText(label)
        self.debug_snapshot_text.setPlainText("Select a debug run to inspect its snapshot.")

    def _refresh_recovery_events(self) -> None:
        self.recovery_list.clear()
        self.recovery_records.clear()
        try:
            records = self.recovery_event_store.load()
        except Exception as exc:
            self.recovery_count_label.setText("Recovery unavailable")
            self.debug_snapshot_text.setPlainText(f"恢复事件不可用：\n{type(exc).__name__}: {exc}")
            return
        records = sorted(records, key=lambda item: item.created_at, reverse=True)[:12]
        self.recovery_count_label.setText(f"{len(records)} event(s)")
        for record in records:
            summary = summarize_recovery_event(record)
            self.recovery_records[summary.id] = summary
            item = QListWidgetItem(recovery_event_label(summary))
            item.setData(Qt.ItemDataRole.UserRole, summary.id)
            item.setToolTip(f"{summary.created_at}\n{summary.path}\n{summary.quarantined_path}")
            self.recovery_list.addItem(item)

    def load_recovery_event_detail(self, item: QListWidgetItem) -> None:
        recovery_id = item.data(Qt.ItemDataRole.UserRole)
        if not recovery_id:
            return
        summary = self.recovery_records.get(str(recovery_id))
        if summary is None:
            return
        self.debug_snapshot_text.setPlainText(recovery_event_detail_text(summary))

    def _refresh_debug_runs(self, trace_id: str) -> None:
        self.debug_list.clear()
        self.debug_records.clear()
        try:
            debug_runs = self.storage.list_debug_runs(trace_id)
        except (KeyError, ValueError):
            self.debug_count_label.setText("Debug runs unavailable")
            return

        self.debug_count_label.setText(f"{len(debug_runs)} snapshot(s)")
        for record in debug_runs:
            summary = summarize_debug_run(record)
            self.debug_records[summary.id] = summary
            item = QListWidgetItem(debug_run_label(summary))
            item.setData(Qt.ItemDataRole.UserRole, summary.id)
            item.setToolTip(f"{summary.created_at}\n{summary.id}")
            self.debug_list.addItem(item)

        if debug_runs:
            first_item = self.debug_list.item(0)
            if first_item is not None:
                self.debug_list.setCurrentItem(first_item)
                self.load_debug_snapshot(first_item)
        else:
            self.debug_snapshot_text.setPlainText("No debug snapshots for this trace.")

    def load_debug_snapshot(self, item: QListWidgetItem) -> None:
        debug_id = item.data(Qt.ItemDataRole.UserRole)
        if not debug_id:
            return
        summary = self.debug_records.get(str(debug_id))
        if summary is None:
            return
        self.debug_snapshot_text.setPlainText(summary.snapshot_text)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.buttons() & Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def _move_to_bottom_right(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        target_width = min(self.width(), max(self.minimumWidth(), available.width() - 48))
        target_height = min(self.height(), max(self.minimumHeight(), available.height() - 48))
        if target_width != self.width() or target_height != self.height():
            self.resize(target_width, target_height)
        self.move(
            available.right() - self.width() - 24,
            available.bottom() - self.height() - 24,
        )

    def _apply_styles(self) -> None:
        self.setFont(QFont("Segoe UI", 10))
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#1d2430"))
        self.setPalette(palette)

        self.setStyleSheet(ASSISTANT_STYLES)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Desktop Assistant")
    lock_file = Path.cwd() / "runtime" / "desktop_assistant_ui.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = str(lock_file)
    lock = QLockFile(lock_path)
    lock.setStaleLockTime(15000)
    if not lock.tryLock(100):
        return 0
    from .desktop_pet_window import DesktopPetWindow
    from .shell_window import AssistantShellWindow

    window = AssistantShellWindow()
    pet_window = DesktopPetWindow(
        state_store=window.state_store,
        on_activate=lambda pet: window.show_from_pet(pet),
        on_reminder_settings=lambda pet: window.show_reminder_settings_from_pet(pet),
        on_quit=window.quit_application,
    )
    window.attach_pet_window(pet_window)
    window.pet_window = pet_window
    pet_window.show()
    try:
        return app.exec()
    finally:
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
