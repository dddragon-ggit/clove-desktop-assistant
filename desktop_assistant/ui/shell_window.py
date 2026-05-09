from __future__ import annotations

import threading

from PySide6.QtCore import QEvent, QObject, QPoint, QThread, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QRegion
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QSizeGrip,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..models import RunMode, WorkflowRequest
from ..todo import ReminderSettings, due_todo_reminders
from ..ui_state import AssistantShellMode, AssistantUiStateStore
from ..sync.config import SupabaseConfigStore
from .shell_controller import AssistantShellController
from .native_window import remove_native_window_frame
from .shell_orb import LivingOrb, PET_WINDOW_HEIGHT, PET_WINDOW_WIDTH
from .shell_pages import ShellPagesMixin
from .shell_reminder_pages import collect_reminder_settings, populate_reminder_settings
from .shell_styles import shell_style
from .shell_tray import (
    TRAY_HEALTH_TEXT,
    TRAY_QUIT_TEXT,
    TRAY_REFRESH_APPS_TEXT,
    TRAY_SHOW_ORB_TEXT,
    TRAY_SHOW_PANEL_TEXT,
    build_tray_icon,
    tray_tooltip,
)
from .shell_todo import ShellTodoMixin
from .shell_workspace_flow import ShellWorkspaceFlowMixin
from . import shell_text
from .view_model import WorkflowSummary, summary_to_plain_text
from .workers import DryRunWorker, ExecuteTraceWorker, worker_failure_text


class AssistantShellWindow(ShellWorkspaceFlowMixin, ShellTodoMixin, ShellPagesMixin, QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.controller = AssistantShellController(sync_service=_build_sync_service())
        self.state_store = AssistantUiStateStore()
        self.drag_position: QPoint | None = None
        self.current_prediction = None
        self.current_suggestion = None
        self.latest_summary: WorkflowSummary | None = None
        self.worker_thread: QThread | None = None
        self.worker = None
        self.is_orb = False
        self._ready = False
        self._suspend_persist = False
        self.tray_icon: QSystemTrayIcon | None = None
        self.tray_menu: QMenu | None = None
        self.tray_show_panel_action: QAction | None = None
        self.tray_show_orb_action: QAction | None = None
        self.pet_window = None

        self.setWindowTitle(shell_text.APP_TITLE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(430, 480)
        self.setFont(QFont("Microsoft YaHei UI", 10))

        self.root = QFrame()
        self.root.setObjectName("shellRoot")
        self.root.setFrameShape(QFrame.Shape.NoFrame)
        self.root.setLineWidth(0)
        self.setCentralWidget(self.root)
        self.root_layout = QVBoxLayout(self.root)
        self.root_layout.setContentsMargins(16, 14, 16, 12)
        self.root_layout.setSpacing(8)
        self.panel_body = QWidget()
        self.orb_body = LivingOrb()
        self.orb_body.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.root_layout.addWidget(self.panel_body)
        self.root_layout.addWidget(self.orb_body)

        self._build_panel()
        self._setup_tray()
        self._install_drag_filters()
        self._apply_shadow()
        self._restore_geometry()
        self._refresh_home()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(30000)
        self.refresh_timer.timeout.connect(self._refresh_home)
        self.refresh_timer.start()
        self.activity_timer = QTimer(self)
        self.activity_timer.setInterval(60000)
        self.activity_timer.timeout.connect(self._sample_activity)
        self.activity_timer.start()
        self.reminder_timer = QTimer(self)
        self.reminder_timer.setInterval(30000)
        self.reminder_timer.timeout.connect(self._check_due_todo_reminders)
        self.reminder_timer.start()
        QTimer.singleShot(1000, self._check_due_todo_reminders)
        QTimer.singleShot(2000, self._initial_sync)
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(5000)
        self.sync_timer.timeout.connect(self._periodic_sync)
        self.sync_timer.start()
        self._ready = True

    def _refresh_home(self) -> None:
        snapshot = self.controller.snapshot()
        self.current_prediction = snapshot.prediction
        self.greeting_label.setText(snapshot.home.greeting)
        self.count_label.setText(shell_text.home_count_text(snapshot.home.important_open_count, snapshot.home.open_count))
        self.next_label.setText(shell_text.next_task_text(snapshot.home.next_task_title, snapshot.home.minutes_until_next))
        self.recovery_label.setText(snapshot.recovery_notice)
        self.recovery_label.setVisible(bool(snapshot.recovery_notice))
        for widget in [self.glance_input, self.menu_input]:
            widget.set_prediction(snapshot.prediction.suggested_text)
        self._populate_todos(snapshot.todos)
        self.orb_body.set_color(snapshot.home.color)
        if self.pet_window is not None:
            self.pet_window.set_status_color(snapshot.home.color)
        self.orb_body.set_hidden_mode(self.state_store.load().orb_hidden)
        self.setStyleSheet(shell_style(snapshot.home.color, orb=self.is_orb))
        self._refresh_tray(snapshot)

    def _initial_sync(self) -> None:
        if self.controller.sync_service is None:
            return
        threading.Thread(target=self._sync_pull_worker, daemon=True).start()

    def _periodic_sync(self) -> None:
        if self.controller.sync_service is None:
            return
        threading.Thread(target=self._sync_pull_worker, daemon=True).start()

    def _sync_pull_worker(self) -> None:
        try:
            stats = self.controller.sync_todos()
            if stats.get("merged_count", 0) > stats.get("local_count", 0):
                QTimer.singleShot(0, self._refresh_home)
        except Exception:
            pass

    def _continue_from_prediction(self) -> None:
        text = self.current_prediction.suggested_text if self.current_prediction else shell_text.CONTINUE_FALLBACK
        self._submit_text(text, True, return_to="menu")

    def _run_dry_run(self, text: str) -> None:
        if not text.strip():
            return
        if self.worker_thread is not None and self.worker_thread.isRunning():
            return
        self.stack.setCurrentWidget(self.chat_page)
        self.chat_text.setPlainText(shell_text.CHAT_PLANNING)
        self.run_once_button.setEnabled(False)
        self.worker_thread = QThread()
        request = WorkflowRequest(user_request=text.strip(), run_mode=RunMode.DRY_RUN)
        self.worker = DryRunWorker(request, self.backend_combo.currentText())
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._dry_run_finished)
        self.worker.failed.connect(self._worker_failed)
        self.worker.progress.connect(self.chat_text.setPlainText)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _dry_run_finished(self, summary: WorkflowSummary) -> None:
        self.latest_summary = summary
        self.chat_text.setPlainText(summary_to_plain_text(summary))
        self.run_once_button.setEnabled(summary.can_run_once)
        self._refresh_home()

    def _execute_latest_trace(self) -> None:
        if self.latest_summary is None or not self.latest_summary.can_run_once:
            return
        if self.worker_thread is not None and self.worker_thread.isRunning():
            return
        self.chat_text.setPlainText(shell_text.CHAT_EXECUTING)
        self.run_once_button.setEnabled(False)
        self.worker_thread = QThread()
        self.worker = ExecuteTraceWorker(self.latest_summary.trace_id)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._dry_run_finished)
        self.worker.failed.connect(self._worker_failed)
        self.worker.progress.connect(self.chat_text.setPlainText)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _worker_failed(self, error: object) -> None:
        self.stack.setCurrentWidget(self.chat_page)
        self.chat_text.setPlainText(worker_failure_text(error))
        self.run_once_button.setEnabled(False)

    def _show_glance(self) -> None:
        self._show_panel()
        self.stack.setCurrentWidget(self.glance_page)

    def _show_menu(self) -> None:
        self._show_panel()
        self.stack.setCurrentWidget(self.menu_page)

    def _show_todo_page(self) -> None:
        self._show_panel()
        self._ensure_compact_panel_geometry()
        self._refresh_home()
        self.stack.setCurrentWidget(self.todo_page)

    def _show_reminder_settings_page(self) -> None:
        self._show_panel()
        self._ensure_work_panel_size(min_width=760, min_height=640)
        populate_reminder_settings(self, self.controller.reminder_settings())
        if hasattr(self, "reminder_settings_feedback"):
            self.reminder_settings_feedback.setText("")
        self.stack.setCurrentWidget(self.reminder_settings_page)

    def _save_reminder_settings(self) -> None:
        settings = collect_reminder_settings(self)
        self.controller.save_reminder_settings(settings)
        self.reminder_settings_feedback.setText(shell_text.REMINDER_SETTINGS_SAVED)

    def _reset_reminder_settings_defaults(self) -> None:
        settings = ReminderSettings()
        self.controller.save_reminder_settings(settings)
        populate_reminder_settings(self, settings)
        self.reminder_settings_feedback.setText(shell_text.REMINDER_SETTINGS_RESET)

    def _show_provider_page(self) -> None:
        self._show_panel()
        self._ensure_work_panel_size(min_width=520, min_height=500)
        self.stack.setCurrentWidget(self.provider_page)

    def _provider_save(self) -> None:
        from .shell_provider_pages import _provider_save
        _provider_save(self)

    def _provider_auto_detect(self) -> None:
        from .shell_provider_pages import _provider_auto_detect
        _provider_auto_detect(self)

    def _provider_test_connection(self) -> None:
        from .shell_provider_pages import _provider_test_connection
        _provider_test_connection(self)

    def _ensure_compact_panel_geometry(self) -> None:
        if self.is_orb:
            self._show_panel()
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        margin = 16
        target_width = min(max(self.minimumWidth(), 520), max(self.minimumWidth(), available.width() - (margin * 2)))
        target_height = min(max(self.minimumHeight(), 560), max(self.minimumHeight(), available.height() - (margin * 2)))
        x = min(max(self.x(), available.left() + margin), available.right() - target_width - margin)
        y = min(max(self.y(), available.top() + margin), available.bottom() - target_height - margin)
        self.setGeometry(x, y, target_width, target_height)

    def _ensure_work_panel_size(self, min_width: int = 620, min_height: int = 640) -> None:
        if self.is_orb:
            self._show_panel()
        target_width = max(self.width(), min_width)
        target_height = max(self.height(), min_height)
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        target_width = min(target_width, max(self.minimumWidth(), available.width() - 32))
        target_height = min(target_height, max(self.minimumHeight(), available.height() - 32))
        if self.width() >= target_width and self.height() >= target_height:
            return
        x = min(max(self.x(), available.left() + 16), available.right() - target_width - 16)
        y = min(max(self.y(), available.top() + 16), available.bottom() - target_height - 16)
        self.setGeometry(x, y, target_width, target_height)

    def _ensure_todo_detail_geometry(self) -> None:
        if self.is_orb:
            self._show_panel()
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        margin = 16
        target_width = max(self.minimumWidth(), min(720, available.width() // 2))
        target_height = max(self.minimumHeight(), min(860, (available.height() * 9) // 10))
        target_width = min(target_width, max(self.minimumWidth(), available.width() - (margin * 2)))
        target_height = min(target_height, max(self.minimumHeight(), available.height() - (margin * 2)))
        x = min(max(self.x(), available.left() + margin), available.right() - target_width - margin)
        y = min(max(self.y(), available.top() + margin), available.bottom() - target_height - margin)
        self.setGeometry(x, y, target_width, target_height)

    def _ensure_workspace_page_geometry(self) -> None:
        if self.is_orb:
            self._show_panel()
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        margin = 16
        target_width = max(self.minimumWidth(), available.width() // 5)
        target_height = max(self.minimumHeight(), (available.height() * 4) // 5)
        target_width = min(target_width, max(self.minimumWidth(), available.width() - (margin * 2)))
        target_height = min(target_height, max(self.minimumHeight(), available.height() - (margin * 2)))
        # Keep the panel close to its current location when switching pages,
        # and only clamp back into the visible desktop if needed.
        x = min(max(self.x(), available.left() + margin), available.right() - target_width - margin)
        y = min(max(self.y(), available.top() + margin), available.bottom() - target_height - margin)
        self.setGeometry(x, y, target_width, target_height)

    def _show_panel(self) -> None:
        if not self.is_orb:
            return
        anchor_x = self.x()
        anchor_y = self.y()
        self._suspend_persist = True
        self.is_orb = False
        self._set_panel_window_mode()
        self.clearMask()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setMinimumSize(430, 480)
        if self.root.graphicsEffect() is None:
            self._apply_shadow()
        self.root_layout.setContentsMargins(16, 14, 16, 12)
        self.root_layout.setSpacing(8)
        self.panel_body.setVisible(True)
        self.orb_body.setVisible(False)
        self.setWindowOpacity(1.0)
        self._restore_panel_geometry(anchor=(anchor_x, anchor_y))
        self._suspend_persist = False
        self._persist_geometry()
        self._refresh_home()

    def _show_orb(self) -> None:
        if self.pet_window is not None:
            self.hide()
            self.pet_window.show()
            self.pet_window.raise_()
            return
        self._persist_geometry()
        anchor_x = self.x()
        anchor_y = self.y()
        self._suspend_persist = True
        self.is_orb = True
        self._set_orb_window_mode()
        self.panel_body.setVisible(False)
        self.orb_body.setVisible(True)
        self.root.setGraphicsEffect(None)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)
        self.setFixedSize(PET_WINDOW_WIDTH, PET_WINDOW_HEIGHT)
        self.clearMask()
        state = self.state_store.load()
        self.orb_body.set_hidden_mode(state.orb_hidden)
        self.setWindowOpacity(0.24 if state.orb_hidden else 0.92)
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        x = min(max(anchor_x, available.left()), available.right() - self.width())
        y = min(max(anchor_y, available.top()), available.bottom() - self.height())
        self.move(x, y)
        self.setStyleSheet(shell_style(self.controller.snapshot().home.color, orb=True))
        remove_native_window_frame(self)
        self._suspend_persist = False
        self.state_store.update_orb(x=self.x(), y=self.y(), hidden=state.orb_hidden)

    def _tray_supported(self) -> bool:
        return bool(QSystemTrayIcon.isSystemTrayAvailable())

    def _setup_tray(self) -> None:
        if not self._tray_supported():
            return
        tray_icon = QSystemTrayIcon(self)
        tray_icon.setIcon(build_tray_icon("#2E7D5B"))
        tray_icon.setToolTip(shell_text.APP_TITLE)
        tray_icon.activated.connect(self._tray_activated)

        menu = QMenu(self)
        show_panel_action = menu.addAction(TRAY_SHOW_PANEL_TEXT)
        show_panel_action.triggered.connect(self._show_panel_from_tray)
        show_orb_action = menu.addAction(TRAY_SHOW_ORB_TEXT)
        show_orb_action.triggered.connect(self._show_orb_from_tray)
        menu.addSeparator()
        health_action = menu.addAction(TRAY_HEALTH_TEXT)
        health_action.triggered.connect(self._show_health_from_tray)
        refresh_apps_action = menu.addAction(TRAY_REFRESH_APPS_TEXT)
        refresh_apps_action.triggered.connect(self._refresh_apps_from_tray)
        menu.addSeparator()
        quit_action = menu.addAction(TRAY_QUIT_TEXT)
        quit_action.triggered.connect(self.quit_application)

        tray_icon.setContextMenu(menu)
        tray_icon.show()

        self.tray_icon = tray_icon
        self.tray_menu = menu
        self.tray_show_panel_action = show_panel_action
        self.tray_show_orb_action = show_orb_action

    def _refresh_tray(self, snapshot) -> None:  # type: ignore[no-untyped-def]
        if self.tray_icon is None:
            return
        self.tray_icon.setIcon(build_tray_icon(snapshot.home.color))
        self.tray_icon.setToolTip(
            tray_tooltip(
                shell_text.APP_TITLE,
                open_count=snapshot.home.open_count,
                next_task_title=snapshot.home.next_task_title,
            )
        )

    def _tray_activated(self, reason) -> None:  # type: ignore[no-untyped-def]
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.MiddleClick,
        }:
            self._show_panel_from_tray()

    def _show_panel_from_tray(self) -> None:
        if self.pet_window is not None:
            self.show_from_pet(self.pet_window)
        elif self.is_orb:
            self._show_glance()
        else:
            self.show()
            self.stack.setCurrentWidget(self.glance_page)
            self._refresh_home()
        self.show()
        self.raise_()
        self.activateWindow()

    def _show_orb_from_tray(self) -> None:
        if self.pet_window is not None:
            self.hide()
            self.pet_window.show()
            self.pet_window.raise_()
            return
        self.show()
        if not self.is_orb:
            self._show_orb()
        self.raise_()
        self.activateWindow()

    def _show_health_from_tray(self) -> None:
        self._show_panel_from_tray()
        snapshot = self.controller.snapshot()
        lines = [
            "健康面板",
            f"待办：{snapshot.home.open_count} 个未完成",
            f"下一项：{snapshot.home.next_task_title or '无'}",
        ]
        if snapshot.recovery_notice:
            lines.extend(["", "最近恢复事件", snapshot.recovery_notice])
        lines.extend(["", self.controller.capability_debug_text()])
        self.chat_text.setPlainText("\n".join(lines))
        self.stack.setCurrentWidget(self.chat_page)

    def _refresh_apps_from_tray(self) -> None:
        try:
            message = self.controller.refresh_app_inventory()
        except Exception as exc:  # noqa: BLE001 - tray action should show a readable failure.
            message = f"刷新应用清单失败：{type(exc).__name__}: {exc}"
        if self.tray_icon is not None:
            self.tray_icon.showMessage("Desktop Assistant", message, QSystemTrayIcon.MessageIcon.Information, 6000)
        if self.pet_window is not None and hasattr(self.pet_window, "show_reminder_bubble"):
            self.pet_window.show_reminder_bubble(message)

    def attach_pet_window(self, pet_window) -> None:  # type: ignore[no-untyped-def]
        self.pet_window = pet_window
        self.state_store = pet_window.state_store
        self._refresh_home()

    def show_from_pet(self, pet_window=None) -> None:  # type: ignore[no-untyped-def]
        source = pet_window or self.pet_window
        if source is not None:
            self._show_panel_near(source.x(), source.y())
        else:
            self._show_panel()
        self.stack.setCurrentWidget(self.glance_page)
        self.show()
        self.raise_()
        self.activateWindow()
        self._refresh_home()

    def show_reminder_settings_from_pet(self, pet_window=None) -> None:  # type: ignore[no-untyped-def]
        self.show_from_pet(pet_window)
        self._show_reminder_settings_page()

    def _show_panel_near(self, anchor_x: int, anchor_y: int) -> None:
        self._suspend_persist = True
        self.is_orb = False
        self._set_panel_window_mode()
        self.clearMask()
        self.setMinimumSize(430, 480)
        if self.root.graphicsEffect() is None:
            self._apply_shadow()
        self.root_layout.setContentsMargins(16, 14, 16, 12)
        self.root_layout.setSpacing(8)
        self.panel_body.setVisible(True)
        self.orb_body.setVisible(False)
        self.setWindowOpacity(1.0)
        width = max(520, self.minimumWidth())
        height = max(420, self.minimumHeight())
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        x = min(max(anchor_x, available.left() + 16), available.right() - width - 16)
        y = min(max(anchor_y, available.top() + 16), available.bottom() - height - 16)
        self.setGeometry(x, y, width, height)
        self._suspend_persist = False

    def trigger_pet_action(self, state: str) -> None:
        if self.pet_window is not None:
            self.pet_window.play_pet_action(state)
        else:
            self.orb_body.play_once(state)

    def hold_pet_state(self, state: str) -> None:
        if self.pet_window is not None:
            self.pet_window.hold_pet_state(state)
        else:
            self.orb_body.hold_state(state)

    def release_pet_hold(self) -> None:
        if self.pet_window is not None:
            self.pet_window.release_pet_hold()
        else:
            self.orb_body.release_hold()

    def _check_due_todo_reminders(self) -> None:
        try:
            reminders = due_todo_reminders(self.controller.snapshot().todos, settings=self.controller.reminder_settings())
        except Exception:  # noqa: BLE001 - reminders should never interrupt the shell.
            return
        if not reminders:
            return
        for reminder in reminders:
            self.controller.record_todo_reminded(reminder.todo.id, reminder_key=reminder.reminder_key)
        self._refresh_home()
        self._show_due_todo_reminder(reminders)

    def _show_due_todo_reminder(self, reminders) -> None:  # type: ignore[no-untyped-def]
        first = reminders[0].todo
        title = _reminder_title(reminders[0].kind)
        if len(reminders) == 1:
            message = f"{title}：{first.title}"
        else:
            message = f"{title}：{first.title} 等 {len(reminders)} 个待办到点"
        if self.tray_icon is not None:
            self.tray_icon.showMessage("Desktop Assistant", message, QSystemTrayIcon.MessageIcon.Information, 8000)
        if self.pet_window is not None and hasattr(self.pet_window, "show_reminder_bubble"):
            self.pet_window.show_reminder_bubble(message)
        else:
            self.trigger_pet_action("waving")

    def quit_application(self) -> None:
        self._persist_geometry()
        if self.pet_window is not None:
            self.pet_window.close()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _quit_from_tray(self) -> None:
        self.quit_application()

    def _set_panel_window_mode(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.root.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.root.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)

    def _set_orb_window_mode(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.root.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.root.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def _restore_geometry(self) -> None:
        state = self.state_store.load()
        if state.mode == AssistantShellMode.ORB:
            self._show_orb()
        else:
            self.setWindowOpacity(1.0)
            self._restore_panel_geometry()
            self.orb_body.setVisible(False)

    def _restore_panel_geometry(self, anchor: tuple[int, int] | None = None) -> None:
        state = self.state_store.load()
        panel = state.panel
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        if panel.width >= 380 and panel.height >= 240:
            target_width = max(430, panel.width)
            target_height = max(360, panel.height)
            if anchor is None:
                self.setGeometry(panel.x, panel.y, target_width, target_height)
                return
            x = min(max(anchor[0], available.left() + 16), available.right() - target_width - 16)
            y = min(max(anchor[1], available.top() + 16), available.bottom() - target_height - 16)
            self.setGeometry(x, y, target_width, target_height)
            return
        width = min(520, max(420, available.width() // 4))
        height = min(380, max(360, available.height() // 3))
        if anchor is not None:
            x = min(max(anchor[0], available.left() + 16), available.right() - width - 16)
            y = min(max(anchor[1], available.top() + 16), available.bottom() - height - 16)
            self.setGeometry(x, y, width, height)
            return
        self.resize(width, height)
        self.move(available.right() - width - 22, available.top() + 22)

    def _persist_geometry(self) -> None:
        if not self._ready or self._suspend_persist:
            return
        if self.is_orb:
            self.state_store.update_orb(x=self.x(), y=self.y())
        else:
            self.state_store.update_panel(x=self.x(), y=self.y(), width=self.width(), height=self.height())

    def _apply_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.root.setGraphicsEffect(shadow)

    def _install_drag_filters(self) -> None:
        self.installEventFilter(self)
        for widget in [self.root, self.panel_body, self.orb_body, *self.panel_body.findChildren(QWidget)]:
            widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, QWidget) and not self._is_interactive_drag_target(watched):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._start_drag(event.globalPosition().toPoint())
                return False
            if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
                if self._move_drag(event.globalPosition().toPoint()):
                    return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._finish_drag()
                return False
        return super().eventFilter(watched, event)

    def _is_interactive_drag_target(self, widget: QWidget) -> bool:
        return isinstance(widget, (QAbstractButton, QComboBox, QLineEdit, QListWidget, QSizeGrip, QTextEdit))

    def _start_drag(self, global_pos: QPoint) -> None:
        self.drag_position = global_pos - self.frameGeometry().topLeft()

    def _move_drag(self, global_pos: QPoint) -> bool:
        if self.drag_position is None:
            return False
        self.move(global_pos - self.drag_position)
        return True

    def _finish_drag(self) -> None:
        if self.drag_position is not None:
            self.drag_position = None
            self._persist_geometry()

    def _sample_activity(self) -> None:
        try:
            self.controller.sample_activity_once()
            self._refresh_home()
        except Exception:  # noqa: BLE001 - activity capture must never interrupt the shell.
            return

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self.is_orb and self.stack.currentWidget() == self.glance_page:
            self._show_menu()
        super().enterEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.is_orb:
            hidden = not self.state_store.load().orb_hidden
            state = self.state_store.update_orb(x=self.x(), y=self.y(), hidden=hidden)
            self.orb_body.set_hidden_mode(state.orb_hidden)
            self.setWindowOpacity(0.24 if state.orb_hidden else 0.92)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.is_orb and event.button() == Qt.MouseButton.LeftButton:
            self._show_glance()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_drag(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.buttons() & Qt.MouseButton.LeftButton and self._move_drag(event.globalPosition().toPoint()):
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._finish_drag()
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._persist_geometry()
        super().resizeEvent(event)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        if self.is_orb:
            remove_native_window_frame(self)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._persist_geometry()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        super().closeEvent(event)


def _reminder_title(kind: str) -> str:
    return {
        "due": shell_text.REMINDER_KIND_DUE,
        "missed": shell_text.REMINDER_KIND_MISSED,
        "repeat": shell_text.REMINDER_KIND_REPEAT,
        "snoozed": shell_text.REMINDER_KIND_SNOOZED,
    }.get(kind, shell_text.REMINDER_KIND_DUE)


def _build_sync_service():  # type: ignore[no-untyped-def]
    try:
        from ..sync.config import SupabaseConfigStore
        from ..sync.supabase_sync import SupabaseSyncService

        config = SupabaseConfigStore().load()
        if not config.enabled or not config.url or not config.key:
            return None
        from supabase import create_client

        client = create_client(config.url, config.key)
        return SupabaseSyncService(client)
    except Exception:
        return None
