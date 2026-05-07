from __future__ import annotations

import unittest
import os
from datetime import UTC, datetime
from pathlib import Path
from shutil import rmtree
from unittest.mock import Mock, patch
from uuid import uuid4

from desktop_assistant.capability.executor import execution_failed, execution_success
from desktop_assistant.confirmation import ConfirmationChoice
from desktop_assistant.habits import NextActionPrediction, NextActionPredictionStore
from desktop_assistant.input_router import InputRouteType
from desktop_assistant.models import ActionPlan, ActionStep, ActionType
from desktop_assistant.storage.recovery_events import RecoveryEventStore
from desktop_assistant.todo import TodoStore, TodoTaskType, TodoWorkspaceHint
from desktop_assistant.ui import shell_text
from desktop_assistant.ui.shell_controller import AssistantShellController
from desktop_assistant.ui.workers import (
    WorkerFailure,
    WorkspaceExecuteWorker,
    WorkspaceExecutionSummary,
    worker_failure_debug_text,
    worker_failure_text,
)
from desktop_assistant.workspace import WorkspaceDraftStore, WorkspaceService, WorkspaceSuggestion


def _workspace_path() -> Path:
    base = Path.cwd() / "runtime" / "test_ui_shell"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


class AssistantShellControllerTests(unittest.TestCase):
    def test_snapshot_reflects_real_todos(self) -> None:
        root = _workspace_path()
        try:
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )

            todo = controller.add_todo("完善新版前端", important=True)
            snapshot = controller.snapshot()

            self.assertEqual(snapshot.home.important_open_count, 1)
            self.assertEqual(snapshot.todos[0].id, todo.id)
        finally:
            rmtree(root, ignore_errors=True)

    def test_controller_adds_todo_with_priority_time_and_postpones(self) -> None:
        root = _workspace_path()
        try:
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )

            todo = controller.add_todo(
                "准备评审",
                important=True,
                priority="urgent",
                reminder_at="2026-04-30T09:00:00+00:00",
            )
            postponed = controller.postpone_todo(todo.id, minutes=30)

            self.assertEqual(todo.priority.value, "urgent")
            self.assertIsNotNone(postponed.snoozed_until)
        finally:
            rmtree(root, ignore_errors=True)

    def test_controller_updates_and_cancels_todo(self) -> None:
        root = _workspace_path()
        try:
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )

            todo = controller.add_todo("旧标题", description="旧说明")
            updated = controller.update_todo(
                todo.id,
                title="新标题",
                description="新说明",
                priority="high",
                important=True,
                reminder_at="2026-05-01T09:00:00+00:00",
            )
            cancelled = controller.cancel_todo(todo.id)

            self.assertEqual(updated.title, "新标题")
            self.assertEqual(updated.description, "新说明")
            self.assertEqual(updated.priority.value, "high")
            self.assertTrue(updated.important)
            self.assertEqual(cancelled.status.value, "cancelled")
            self.assertEqual(controller.snapshot().todos, [])
        finally:
            rmtree(root, ignore_errors=True)

    def test_controller_updates_todo_workspace_binding(self) -> None:
        root = _workspace_path()
        try:
            store = TodoStore(root / "todos.json")
            controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            todo = controller.add_todo("准备工作区")

            updated = controller.update_todo_workspace(
                todo.id,
                workspace=TodoWorkspaceHint(apps=["Cursor"], urls=["https://example.com"]),
                needs_computer=True,
            )

            self.assertTrue(updated.needs_computer)
            self.assertEqual(updated.workspace.apps, ["Cursor"])
            self.assertEqual(updated.workspace.urls, ["https://example.com"])
        finally:
            rmtree(root, ignore_errors=True)

    def test_snapshot_includes_recent_recovery_notice(self) -> None:
        root = _workspace_path()
        try:
            recovery_store = RecoveryEventStore(root / "recovery_events.json")
            recovery_store.append(
                source="todo_store",
                category="todo_store_corrupted",
                path=root / "todos.json",
                quarantined_path=root / "todos.json.corrupt",
                reason="Todo JSON is unreadable.",
            )
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            controller.recovery_event_store = recovery_store

            snapshot = controller.snapshot()

            self.assertIn("待办数据异常", snapshot.recovery_notice)
            self.assertIn("todos.json.corrupt", snapshot.recovery_notice)
        finally:
            rmtree(root, ignore_errors=True)


class ShellTextTests(unittest.TestCase):
    def test_shell_text_catalog_has_no_mojibake(self) -> None:
        values = []
        for name in dir(shell_text):
            if not name.isupper():
                continue
            value = getattr(shell_text, name)
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, tuple):
                values.extend(str(part) for item in value for part in (item if isinstance(item, tuple) else (item,)))

        joined = "\n".join(values)
        for marker in ["Ã", "Â", "æ", "å", "ç", "è", "é", "杈", "涓", "�"]:
            self.assertNotIn(marker, joined)


class WorkerFailureFormattingTests(unittest.TestCase):
    def test_worker_failure_text_and_debug_text_are_product_readable(self) -> None:
        failure = WorkerFailure(
            stage="dry_run",
            error_type="RuntimeError",
            message="boom",
            details="traceback lines",
            user_message="预演规划过程中出现异常。",
        )

        text = worker_failure_text(failure)
        debug_text = worker_failure_debug_text(failure)

        self.assertIn("预演规划过程中出现异常。", text)
        self.assertIn("RuntimeError: boom", text)
        self.assertIn("需要查看完整错误堆栈", text)
        self.assertIn("traceback lines", debug_text)


class AssistantShellWindowTests(unittest.TestCase):
    def test_shell_style_uses_mudie_panel_theme(self) -> None:
        from desktop_assistant.ui.shell_styles import shell_style

        style = shell_style("#C2413B")

        self.assertIn("#f7b1dc", style.lower())
        self.assertIn("#dceaff", style.lower())
        self.assertIn("qlineargradient", style)
        self.assertIn("QFrame#shellSurface", style)
        self.assertIn("QFrame#pageAccent", style)
        self.assertIn("rgba(207, 92, 98", style)

    def test_recovery_panel_loads_recent_events(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.app import FloatingAssistantWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = FloatingAssistantWindow()
        try:
            recovery_store = RecoveryEventStore(root / "recovery_events.json")
            recovery_store.append(
                source="todo_store",
                category="todo_store_corrupted",
                path=root / "todos.json",
                quarantined_path=root / "todos.json.corrupt",
                reason="Todo JSON is unreadable.",
            )
            window.recovery_event_store = recovery_store

            window._refresh_recovery_events()
            app.processEvents()

            self.assertEqual(window.recovery_list.count(), 1)
            item = window.recovery_list.item(0)
            self.assertIn("待办", item.text())
            window.load_recovery_event_detail(item)
            self.assertIn("隔离文件", window.debug_snapshot_text.toPlainText())
            self.assertIn("todos.json.corrupt", window.debug_snapshot_text.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_panel_minimize_hides_panel_when_persistent_pet_is_attached(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui.shell_window import AssistantShellWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            window = AssistantShellWindow()
            window.state_store = AssistantUiStateStore(root / "ui_state.json")
            pet = DesktopPetWindow(state_store=window.state_store, on_activate=lambda source: window.show_from_pet(source))
            window.attach_pet_window(pet)
            window.resize(540, 380)
            window.move(0, 0)
            window.show()
            pet.show()
            app.processEvents()

            window._show_orb()
            app.processEvents()

            self.assertFalse(window.isVisible())
            self.assertTrue(pet.isVisible())

            window.show_from_pet(pet)
            app.processEvents()

            self.assertFalse(window.is_orb)
            self.assertTrue(window.isVisible())
            self.assertEqual((window.width(), window.height()), (520, 420))
            self.assertIsNotNone(window.root.graphicsEffect())
            self.assertTrue(window.mask().isEmpty())
            image = window.grab().toImage()
            self.assertLess(image.pixelColor(0, 0).alpha(), 20)
            self.assertGreater(image.pixelColor(window.width() // 2, window.height() // 2).alpha(), 245)
            pet.close()
            window.close()
        finally:
            rmtree(root, ignore_errors=True)

    def test_panel_appears_near_persistent_pet_position(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui.shell_window import AssistantShellWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            window = AssistantShellWindow()
            window.state_store = AssistantUiStateStore(root / "ui_state.json")
            pet = DesktopPetWindow(state_store=window.state_store, on_activate=lambda source: window.show_from_pet(source))
            window.attach_pet_window(pet)
            pet.move(180, 140)
            pet.show()
            window.show()
            app.processEvents()

            window.move(40, 40)
            window.resize(700, 600)
            window.hide()
            window.show_from_pet(pet)
            app.processEvents()

            self.assertFalse(window.is_orb)
            self.assertEqual(window.x(), 180)
            self.assertEqual(window.y(), 140)
            self.assertEqual((window.width(), window.height()), (520, 420))
            pet.close()
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_quit_application_closes_persistent_pet(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui.shell_window import AssistantShellWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            window = AssistantShellWindow()
            window.state_store = AssistantUiStateStore(root / "ui_state.json")
            pet = DesktopPetWindow(state_store=window.state_store, on_activate=lambda source: window.show_from_pet(source))
            window.attach_pet_window(pet)
            window.show()
            pet.show()
            app.processEvents()

            window.quit_application()
            app.processEvents()

            self.assertFalse(window.isVisible())
            self.assertFalse(pet.isVisible())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_desktop_pet_quit_uses_quit_callback(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            quit_callback = Mock()
            pet = DesktopPetWindow(state_store=AssistantUiStateStore(root / "ui_state.json"), on_quit=quit_callback)
            pet.quit_application()
            app.processEvents()

            quit_callback.assert_called_once_with()
            pet.close()
        finally:
            rmtree(root, ignore_errors=True)

    def test_panel_close_button_hides_panel_but_keeps_persistent_pet(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QPushButton
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui.shell_window import AssistantShellWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            window = AssistantShellWindow()
            window.state_store = AssistantUiStateStore(root / "ui_state.json")
            pet = DesktopPetWindow(state_store=window.state_store, on_activate=lambda source: window.show_from_pet(source))
            window.attach_pet_window(pet)
            window.show()
            pet.show()
            app.processEvents()

            close_button = next(button for button in window.findChildren(QPushButton) if button.text() == shell_text.CLOSE)
            close_button.click()
            app.processEvents()

            self.assertFalse(window.isVisible())
            self.assertTrue(pet.isVisible())
        finally:
            pet.close()
            window.close()
            rmtree(root, ignore_errors=True)

    def test_desktop_pet_bubble_menu_has_readable_options(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QPushButton
        from desktop_assistant.ui.desktop_pet_window import (
            PET_MENU_QUIT_TEXT,
            PET_MENU_REMINDER_SETTINGS_TEXT,
            PET_MENU_SHOW_PANEL_TEXT,
            PetBubbleButton,
            PetBubbleLabel,
            PetBubbleMenu,
        )

        app = QApplication.instance() or QApplication([])
        menu = PetBubbleMenu(hidden=False, on_show_panel=Mock(), on_reminder_settings=Mock(), on_quit=Mock())
        try:
            menu.show()
            app.processEvents()

            buttons = menu.findChildren(QPushButton)
            texts = [button.text() for button in buttons]
            self.assertEqual(texts, [PET_MENU_SHOW_PANEL_TEXT, PET_MENU_REMINDER_SETTINGS_TEXT, PET_MENU_QUIT_TEXT])
            self.assertTrue(all(button.styleSheet() or menu.styleSheet() for button in buttons))
            self.assertEqual([button.objectName() for button in buttons], ["petBubbleOption", "petBubbleOption", "petBubbleQuit"])
            self.assertTrue(all(isinstance(button, PetBubbleButton) for button in buttons))
            self.assertEqual(len(menu.findChildren(PetBubbleLabel)), 1)
            self.assertTrue(all(button.visual_width() < menu.width() for button in buttons))
            self.assertIs(menu._title_bubble(), menu.findChildren(PetBubbleLabel)[0])
            self.assertEqual(buttons[0]._text_color(1.0).name(), "#2c3758")
            self.assertEqual(buttons[-1]._text_color(1.0).name(), "#7e365b")
            self.assertTrue(menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
            self.assertTrue(menu.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground))
            self.assertTrue(bool(menu.windowFlags() & Qt.WindowType.NoDropShadowWindowHint))
            self.assertIn("background: transparent", menu.styleSheet())
        finally:
            menu.close()

    def test_desktop_pet_uses_embedded_bubble_menu_without_native_frame(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication, QPushButton
        from desktop_assistant.ui.desktop_pet_window import BUBBLE_MENU_WIDTH, DesktopPetWindow, PET_WINDOW_HEIGHT, PET_WINDOW_WIDTH
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            pet = DesktopPetWindow(state_store=AssistantUiStateStore(root / "ui_state.json"))
            pet.show()
            app.processEvents()

            pet._show_bubble_menu(QPoint(pet.x(), pet.y()))
            app.processEvents()

            self.assertIsNotNone(pet.bubble_menu)
            self.assertIs(pet.bubble_menu.parentWidget(), pet)
            self.assertFalse(pet.bubble_menu.isWindow())
            self.assertGreaterEqual(pet.width(), BUBBLE_MENU_WIDTH)
            self.assertTrue(pet.pet.isVisible())
            self.assertEqual((pet.pet.width(), pet.pet.height()), (PET_WINDOW_WIDTH, PET_WINDOW_HEIGHT))
            self.assertEqual((pet.pet.x(), pet.pet.y()), (pet._pet_offset.x(), pet._pet_offset.y()))
            self.assertFalse(pet.bubble_menu.geometry().intersects(pet.pet.geometry()))
            for button in pet.bubble_menu.findChildren(QPushButton):
                right_edge = pet.bubble_menu.x() + button.geometry().right()
                if pet._pet_offset.x() > 0:
                    self.assertLess(right_edge, pet._pet_offset.x())
                else:
                    self.assertGreaterEqual(pet.bubble_menu.x(), PET_WINDOW_WIDTH)

            pet.dismiss_bubble_menu()
            app.processEvents()
            self.assertEqual(pet.width(), PET_WINDOW_WIDTH)
            self.assertEqual((pet.pet.x(), pet.pet.y()), (0, 0))
        finally:
            pet.close()
            rmtree(root, ignore_errors=True)

    def test_desktop_pet_click_can_dismiss_bubble_menu(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            pet = DesktopPetWindow(state_store=AssistantUiStateStore(root / "ui_state.json"))
            pet.show()
            pet._show_bubble_menu(QPoint(pet.x(), pet.y()))
            app.processEvents()

            self.assertIsNotNone(pet.bubble_menu)
            self.assertTrue(pet.dismiss_bubble_menu())
            app.processEvents()
            self.assertIsNone(pet.bubble_menu)
            self.assertFalse(pet.dismiss_bubble_menu())
        finally:
            pet.close()
            rmtree(root, ignore_errors=True)

    def test_desktop_pet_right_click_toggles_hidden_without_menu(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            pet = DesktopPetWindow(state_store=AssistantUiStateStore(root / "ui_state.json"))
            pet.show()
            app.processEvents()

            press_global = pet.mapToGlobal(QPoint(24, 24))
            event = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(24, 24),
                QPointF(press_global),
                Qt.MouseButton.RightButton,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
            )

            self.assertTrue(pet.eventFilter(pet.pet, event))
            self.assertIsNone(pet.bubble_menu)
            self.assertTrue(pet._right_click_timer.isActive())
            pet._complete_right_click()
            app.processEvents()

            self.assertTrue(pet.state_store.load().orb_hidden)
            self.assertIsNone(pet.bubble_menu)
        finally:
            pet.close()
            rmtree(root, ignore_errors=True)

    def test_desktop_pet_right_double_click_opens_bubble_menu(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            pet = DesktopPetWindow(state_store=AssistantUiStateStore(root / "ui_state.json"))
            pet.show()
            app.processEvents()

            press_global = pet.mapToGlobal(QPoint(24, 24))
            press = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(24, 24),
                QPointF(press_global),
                Qt.MouseButton.RightButton,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
            )
            double = QMouseEvent(
                QEvent.Type.MouseButtonDblClick,
                QPointF(24, 24),
                QPointF(press_global),
                Qt.MouseButton.RightButton,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
            )

            self.assertTrue(pet.eventFilter(pet.pet, press))
            self.assertTrue(pet._right_click_timer.isActive())
            self.assertTrue(pet.eventFilter(pet.pet, double))
            app.processEvents()

            self.assertFalse(pet._right_click_timer.isActive())
            self.assertFalse(pet.state_store.load().orb_hidden)
            self.assertIsNotNone(pet.bubble_menu)
        finally:
            pet.close()
            rmtree(root, ignore_errors=True)

    def test_desktop_pet_drag_can_start_while_dismissing_bubble_menu(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            pet = DesktopPetWindow(state_store=AssistantUiStateStore(root / "ui_state.json"))
            pet.move(200, 120)
            pet.show()
            pet._show_bubble_menu(QPoint(pet.x(), pet.y()))
            app.processEvents()

            press_global = pet.mapToGlobal(pet._pet_offset + QPoint(24, 24))
            event = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(24, 24),
                QPointF(press_global),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )

            handled = pet.eventFilter(pet.pet, event)
            app.processEvents()

            self.assertTrue(handled)
            self.assertIsNone(pet.bubble_menu)
            self.assertIsNotNone(pet.drag_position)
            self.assertTrue(pet._drag_has_mouse_grab)
            self.assertEqual(pet.cursor().shape(), Qt.CursorShape.ClosedHandCursor)
            self.assertEqual(pet.pet._state, "jumping")

            move_global = press_global + QPoint(36, 28)
            move_event = QMouseEvent(
                QEvent.Type.MouseMove,
                QPointF(60, 52),
                QPointF(move_global),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            pet.mouseMoveEvent(move_event)
            app.processEvents()
            self.assertEqual((pet.x(), pet.y()), (236, 148))
            self.assertEqual(pet.pet._state, "running-right")
            pet._finish_drag()
            self.assertFalse(pet._drag_has_mouse_grab)
            self.assertEqual(pet.pet._state, "jumping")
        finally:
            pet.close()
            rmtree(root, ignore_errors=True)

    def test_desktop_pet_bubbles_reveal_from_source_point(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import PetBubbleButton, PetBubbleLabel, PetBubbleMenu

        app = QApplication.instance() or QApplication([])
        menu = PetBubbleMenu(hidden=False, on_show_panel=Mock(), on_reminder_settings=Mock(), on_quit=Mock())
        try:
            menu.set_source_point(QPointF(245, 40))
            menu.show()
            app.processEvents()

            bubbles = [*menu.findChildren(PetBubbleLabel), *menu.findChildren(PetBubbleButton)]
            self.assertEqual(len(bubbles), 4)
            self.assertTrue(all(bubble._reveal_progress <= 1.0 for bubble in bubbles))

            for bubble in bubbles:
                bubble.set_reveal_progress(1.0)
            app.processEvents()

            self.assertTrue(all(bubble._reveal_progress == 1.0 for bubble in bubbles))
            self.assertTrue(all(bubble.tail_point().x() > 0 for bubble in bubbles))
        finally:
            menu.close()

    def test_desktop_pet_can_show_reminder_bubble(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            pet = DesktopPetWindow(state_store=AssistantUiStateStore(root / "ui_state.json"))
            pet.show()
            app.processEvents()

            pet.show_reminder_bubble("提醒：写周报")
            app.processEvents()

            self.assertIsNotNone(pet.reminder_bubble)
            self.assertIsNone(pet.bubble_menu)
            self.assertTrue(pet._reminder_close_timer.isActive())
            self.assertIs(pet.reminder_bubble.parentWidget(), pet)
            self.assertFalse(pet.reminder_bubble.geometry().intersects(pet.pet.geometry()))
            self.assertIn("写周报", pet.reminder_bubble.bubble_label().text())
        finally:
            pet.close()
            rmtree(root, ignore_errors=True)

    def test_desktop_pet_reminder_bubble_uses_user_reply_buttons(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow, PetBubbleButton
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            pet = DesktopPetWindow(state_store=AssistantUiStateStore(root / "ui_state.json"))
            selected = Mock()
            pet.show()
            app.processEvents()

            pet.show_reminder_bubble("提醒：写周报", actions=[("稍后提醒", selected)])
            app.processEvents()

            self.assertIsNotNone(pet.reminder_bubble)
            buttons = pet.reminder_bubble.action_buttons()
            self.assertEqual([button.text() for button in buttons], ["稍后提醒"])
            self.assertTrue(all(isinstance(button, PetBubbleButton) for button in buttons))
            self.assertEqual(buttons[0]._text_color(1.0).name(), "#2c3758")
            self.assertEqual(len(pet.reminder_bubble._birth_bubbles()), 2)

            buttons[0].click()
            app.processEvents()

            selected.assert_called_once()
            self.assertIsNone(pet.reminder_bubble)
        finally:
            pet.close()
            rmtree(root, ignore_errors=True)

    def test_legacy_orb_uses_current_panel_position_when_no_persistent_pet(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            window = AssistantShellWindow()
            window.state_store = AssistantUiStateStore(root / "ui_state.json")
            window.resize(540, 380)
            window.move(210, 160)
            window.show()
            app.processEvents()

            window._show_orb()
            app.processEvents()

            self.assertTrue(window.is_orb)
            self.assertEqual(window.x(), 210)
            self.assertEqual(window.y(), 160)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_system_tray_icon_is_created_when_supported(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_tray import (
            TRAY_HEALTH_TEXT,
            TRAY_QUIT_TEXT,
            TRAY_REFRESH_APPS_TEXT,
            TRAY_SHOW_ORB_TEXT,
            TRAY_SHOW_PANEL_TEXT,
        )
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        with patch("desktop_assistant.ui.shell_window.QSystemTrayIcon.isSystemTrayAvailable", return_value=True):
            window = AssistantShellWindow()
            try:
                window.show()
                app.processEvents()

                self.assertIsNotNone(window.tray_icon)
                self.assertIsNotNone(window.tray_menu)
                texts = [action.text() for action in window.tray_menu.actions() if action.text()]
                self.assertIn(TRAY_SHOW_PANEL_TEXT, texts)
                self.assertIn(TRAY_SHOW_ORB_TEXT, texts)
                self.assertIn(TRAY_HEALTH_TEXT, texts)
                self.assertIn(TRAY_REFRESH_APPS_TEXT, texts)
                self.assertIn(TRAY_QUIT_TEXT, texts)
            finally:
                window.close()

    def test_desktop_ui_lock_prevents_duplicate_instances(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QLockFile
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        root = _workspace_path()
        try:
            lock_path = str(root / "desktop_assistant_ui.lock")
            first = QLockFile(lock_path)
            second = QLockFile(lock_path)

            self.assertTrue(first.tryLock(100))
            self.assertFalse(second.tryLock(100))
            first.unlock()
            self.assertTrue(second.tryLock(100))
            second.unlock()
        finally:
            rmtree(root, ignore_errors=True)

    def test_tray_panel_action_restores_from_orb(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        with patch("desktop_assistant.ui.shell_window.QSystemTrayIcon.isSystemTrayAvailable", return_value=True):
            window = AssistantShellWindow()
            try:
                window.show()
                app.processEvents()

                window._show_orb()
                app.processEvents()
                window._show_panel_from_tray()
                app.processEvents()

                self.assertFalse(window.is_orb)
                self.assertIs(window.stack.currentWidget(), window.glance_page)
            finally:
                window.close()

    def test_living_orb_renders_status_color_and_hidden_mode(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_orb import LivingOrb

        app = QApplication.instance() or QApplication([])
        orb = LivingOrb()
        orb.resize(124, 146)
        orb.show()
        orb.set_color("#C2413B")
        orb.set_hidden_mode(False)
        app.processEvents()

        self.assertEqual((orb.width(), orb.height()), (124, 146))
        visible = orb.grab().toImage()
        self.assertLess(visible.pixelColor(0, 0).alpha(), 20)
        center = visible.pixelColor(orb.width() // 2, orb.height() // 2)
        self.assertGreater(center.alpha(), 80)
        self.assertGreater(center.blue(), 40)
        badge_pixels = [
            visible.pixelColor(x, y)
            for x in range(orb.width() - 26, orb.width() - 8)
            for y in range(4, 18)
            if visible.pixelColor(x, y).alpha() > 60
        ]
        self.assertTrue(badge_pixels)
        self.assertTrue(any(color.red() > color.green() for color in badge_pixels))

        orb.set_hidden_mode(True)
        app.processEvents()
        hidden = orb.grab().toImage().pixelColor(orb.width() // 2, orb.height() // 2)
        self.assertLess(hidden.alpha(), center.alpha())
        orb.close()

    def test_living_orb_loads_packaged_pet_when_available(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QColor, QImage
        from PySide6.QtCore import Qt
        from desktop_assistant.ui.shell_orb import LivingOrb

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        pet_dir = root / "pet"
        try:
            pet_dir.mkdir(parents=True, exist_ok=True)
            sheet = QImage(1536, 1872, QImage.Format.Format_ARGB32_Premultiplied)
            sheet.fill(Qt.GlobalColor.transparent)
            for x in range(24, 168):
                for y in range(24, 184):
                    sheet.setPixelColor(x, y, QColor("#4F9BFF"))
            sheet.save(str(pet_dir / "spritesheet.png"))
            (pet_dir / "pet.json").write_text(
                '{"id":"mudie","displayName":"Mudie","description":"test","spritesheetPath":"spritesheet.png"}',
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"DESKTOP_ASSISTANT_PET_DIR": str(pet_dir)}):
                orb = LivingOrb()
                orb.resize(124, 146)
                orb.show()
                app.processEvents()

                image = orb.grab().toImage()
                center = image.pixelColor(orb.width() // 2, orb.height() // 2)
                self.assertGreater(center.blue(), 120)
                self.assertGreater(center.alpha(), 80)
                orb.close()
        finally:
            rmtree(root, ignore_errors=True)

    def test_living_orb_finds_project_runtime_pet_when_cwd_changes(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from pathlib import Path
        from shutil import rmtree
        from uuid import uuid4
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_orb import LivingOrb

        app = QApplication.instance() or QApplication([])
        original_cwd = Path.cwd()
        pet_manifest = original_cwd / "runtime" / "pets" / "mudie" / "pet.json"
        if not pet_manifest.exists():
            self.skipTest("Packaged runtime pet is not available.")
        temp_dir = original_cwd / "runtime" / "test_tmp" / uuid4().hex
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chdir(temp_dir)
            orb = LivingOrb()
            orb.resize(124, 146)
            orb.show()
            app.processEvents()

            self.assertIsNotNone(orb._package)
            self.assertEqual(orb._package.pet_id, "mudie")
            orb.close()
        finally:
            os.chdir(original_cwd)
            rmtree(temp_dir, ignore_errors=True)

    def test_living_orb_supports_one_shot_and_held_actions(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_orb import LivingOrb

        app = QApplication.instance() or QApplication([])
        orb = LivingOrb()
        orb.show()
        try:
            orb.set_color("#2E7D5B")
            orb.play_once("waving")
            app.processEvents()
            self.assertEqual(orb._state, "waving")

            orb.hold_state("running")
            app.processEvents()
            self.assertEqual(orb._state, "running")

            orb.release_hold()
            app.processEvents()
            self.assertEqual(orb._state, "idle")
            self.assertLessEqual(orb._ambient_timer.interval(), 9000)
        finally:
            orb.close()

    def test_living_orb_drag_state_temporarily_overrides_other_actions(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_orb import LivingOrb

        app = QApplication.instance() or QApplication([])
        orb = LivingOrb()
        orb.show()
        try:
            orb.hold_state("running")
            app.processEvents()
            self.assertEqual(orb._state, "running")

            orb.hold_drag_state("running-left")
            app.processEvents()
            self.assertEqual(orb._state, "running-left")

            orb.play_once("waving")
            app.processEvents()
            self.assertEqual(orb._state, "running-left")

            orb.release_drag_state()
            app.processEvents()
            self.assertEqual(orb._state, "waving")

            orb._oneshot_state = None
            orb.release_hold()
            app.processEvents()
            self.assertEqual(orb._state, orb._base_state)
        finally:
            orb.close()

    def test_living_orb_ambient_action_is_easy_to_notice(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_orb import LivingOrb

        app = QApplication.instance() or QApplication([])
        orb = LivingOrb()
        orb.show()
        try:
            app.processEvents()
            orb.set_color("#2E7D5B")
            orb._play_ambient()
            app.processEvents()
            self.assertEqual(orb._state, "waving")

            orb._oneshot_state = None
            orb.set_color("#2E7D5B")
            orb._play_ambient()
            app.processEvents()
            self.assertEqual(orb._state, "jumping")
        finally:
            orb.close()

    def test_shell_pet_actions_forward_to_persistent_pet(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.desktop_pet_window import DesktopPetWindow
        from desktop_assistant.ui.shell_window import AssistantShellWindow
        from desktop_assistant.ui_state import AssistantUiStateStore

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            window.state_store = AssistantUiStateStore(root / "ui_state.json")
            pet = DesktopPetWindow(state_store=window.state_store, on_activate=lambda source: window.show_from_pet(source))
            window.attach_pet_window(pet)
            pet.show()

            window.trigger_pet_action("jumping")
            app.processEvents()
            self.assertEqual(pet.pet._state, "jumping")

            window.hold_pet_state("running")
            app.processEvents()
            self.assertEqual(pet.pet._state, "running")

            window.release_pet_hold()
            app.processEvents()
            self.assertEqual(pet.pet._state, pet.pet._base_state)
            pet.close()
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_menu_buttons_have_room_in_minimum_panel_size(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QPushButton
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        window = AssistantShellWindow()
        try:
            window.resize(window.minimumSize())
            window.show()
            window._show_menu()
            app.processEvents()

            buttons = [
                button
                for button in window.menu_page.findChildren(QPushButton)
                if button.objectName() == "navButton"
            ]

            self.assertEqual(len(buttons), 3)
            for current, next_button in zip(buttons, buttons[1:]):
                self.assertLess(current.geometry().bottom(), next_button.geometry().top())
        finally:
            window.close()

    def test_todo_page_controls_have_room_at_minimum_panel_size(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        window = AssistantShellWindow()
        try:
            window.resize(window.minimumSize())
            window.show()
            window._show_todo_page()
            app.processEvents()

            controls = [
                window.todo_list,
                window.todo_quick_input,
            ]
            for widget in controls:
                self.assertGreater(widget.geometry().width(), 20)
                self.assertGreater(widget.geometry().height(), 10)
            self.assertIs(window.stack.currentWidget(), window.todo_page)
            self.assertFalse(window.todo_detail.isVisible())
        finally:
            window.close()

    def test_todo_page_opens_global_reminder_settings(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QPushButton
        from desktop_assistant.todo import ReminderSettingsStore
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                reminder_settings_store=ReminderSettingsStore(root / "reminder_settings.json"),
            )
            window.show()
            window._show_todo_page()
            app.processEvents()

            button = next(
                item
                for item in window.todo_page.findChildren(QPushButton)
                if item.text() == shell_text.TODO_REMINDER_SETTINGS
            )
            button.click()
            app.processEvents()

            self.assertIs(window.stack.currentWidget(), window.reminder_settings_page)
            self.assertEqual(window.reminder_daily_reset_spin.value(), 4)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_reminder_settings_page_saves_global_policy(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.todo import ReminderSettingsStore
        from desktop_assistant.todo.reminder_settings import reminder_policy_key
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            settings_store = ReminderSettingsStore(root / "reminder_settings.json")
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                reminder_settings_store=settings_store,
            )
            window.show()
            window._show_reminder_settings_page()
            app.processEvents()

            key = reminder_policy_key(TodoTaskType.DAILY, "urgent")
            controls = window.reminder_policy_controls[key]
            controls["repeat_minutes"].setValue(12)
            controls["max_repeats"].setValue(5)
            controls["snooze_minutes"].setValue(45)
            window.reminder_quiet_start_input.setText("22:15")
            window.reminder_daily_reset_spin.setValue(5)
            window._save_reminder_settings()

            saved = settings_store.load()
            policy = saved.policies[key]
            self.assertEqual(saved.quiet_start, "22:15")
            self.assertEqual(saved.daily_reset_hour, 5)
            self.assertEqual(policy.repeat_minutes, 12)
            self.assertEqual(policy.max_repeats, 5)
            self.assertEqual(policy.snooze_minutes, 45)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_shell_work_pages_use_unified_surface_cards(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QFrame, QPushButton
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        window = AssistantShellWindow()
        try:
            window.resize(window.minimumSize())
            window.show()
            app.processEvents()

            def surfaces(page):
                return [frame for frame in page.findChildren(QFrame) if frame.objectName() == "shellSurface"]

            self.assertGreaterEqual(len(surfaces(window.todo_page)), 2)
            self.assertGreaterEqual(len(surfaces(window.todo_detail_page)), 4)
            self.assertGreaterEqual(len(surfaces(window.workspace_page)), 4)
            self.assertGreaterEqual(len(surfaces(window.workspace_confirm_page)), 2)

            window._show_workspace_page()
            app.processEvents()
            controls = [
                window.workspace_input,
                window.workspace_recipe_combo,
                window.workspace_plan_action_list,
                window.workspace_plan_action_type_combo,
                window.workspace_plan_action_target_input,
                window.feedback_input,
            ]
            for widget in controls:
                self.assertGreater(widget.geometry().width(), 20)
                self.assertGreater(widget.geometry().height(), 10)
            add_button = next(
                button
                for button in window.workspace_page.findChildren(QPushButton)
                if button.text() == shell_text.TODO_ADD_WORKSPACE_ACTION
            )
            self.assertLess(window.workspace_plan_action_target_input.geometry().bottom(), add_button.geometry().top())
        finally:
            window.close()

    def test_workspace_page_uses_tall_sidebar_geometry(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        window = AssistantShellWindow()
        try:
            window.show()
            app.processEvents()
            before_x = window.x()
            before_y = window.y()
            window._show_workspace_page()
            app.processEvents()

            screen = window.screen() or QApplication.primaryScreen()
            available = screen.availableGeometry() if screen else window.geometry()
            expected_width = min(
                max(window.minimumWidth(), available.width() // 5),
                max(window.minimumWidth(), available.width() - 32),
            )
            expected_height = min(
                max(window.minimumHeight(), (available.height() * 4) // 5),
                max(window.minimumHeight(), available.height() - 32),
            )

            self.assertEqual(window.width(), expected_width)
            self.assertEqual(window.height(), expected_height)
            self.assertEqual(window.x(), before_x)
            self.assertEqual(window.y(), before_y)
            self.assertIs(window.stack.currentWidget(), window.workspace_page)
        finally:
            window.close()

    def test_todo_list_click_opens_detail_and_uses_urgency_colors(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QScrollArea
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            store.create("普通待办")
            store.create("紧急待办", priority="urgent")
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window.resize(430, 360)
            window._show_todo_page()
            app.processEvents()

            self.assertEqual(window._todo_item_count(), 2)
            first_color = window._todo_item_at(0).background().color()
            second_color = window._todo_item_at(1).background().color()
            self.assertNotEqual(first_color.getRgb(), second_color.getRgb())
            self.assertFalse(window.todo_detail.isVisible())

            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            app.processEvents()
            screen = window.screen() or QApplication.primaryScreen()
            available = screen.availableGeometry() if screen else window.geometry()
            expected_height = max(
                window.minimumHeight(),
                min(860, (available.height() * 9) // 10),
            )
            expected_height = min(
                expected_height,
                max(window.minimumHeight(), available.height() - 32),
            )

            self.assertIs(window.stack.currentWidget(), window.todo_detail_page)
            self.assertTrue(window.todo_detail.isVisible())
            self.assertGreaterEqual(window.width(), 430)
            self.assertEqual(window.height(), expected_height)
            self.assertIsNotNone(window.findChild(QScrollArea, "todoDetailScroll"))
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_todo_detail_geometry_resets_each_time_page_is_reopened(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            store.create("准备资料")
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window._show_todo_page()
            app.processEvents()

            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            app.processEvents()
            expected_width = window.width()
            expected_height = window.height()

            window.resize(expected_width + 180, expected_height + 120)
            app.processEvents()
            self.assertGreater(window.width(), expected_width)
            self.assertGreater(window.height(), expected_height)

            window._show_todo_page()
            app.processEvents()
            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            app.processEvents()

            self.assertEqual(window.width(), expected_width)
            self.assertEqual(window.height(), expected_height)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_clicking_todo_builds_workspace_preview(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QPushButton
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            store.create(
                "写周报",
                needs_computer=True,
                workspace=TodoWorkspaceHint(apps=["Cursor"], urls=["https://example.com"]),
            )
            window.controller = controller
            window.show()
            window._show_todo_page()
            app.processEvents()

            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            app.processEvents()

            detail = window.todo_detail.toPlainText()
            self.assertIn("这个任务建议先这样准备", detail)
            self.assertIn("点“现在准备”", detail)
            self.assertIn("确认", detail)
            self.assertIn("打开应用", detail)
            self.assertIn("https://example.com", detail)
            self.assertTrue(any(button.text() == shell_text.TODO_PREPARE_WORKSPACE for button in window.todo_detail_page.findChildren(QPushButton)))
            self.assertTrue(window.todo_run_once_button.isEnabled())
            self.assertFalse(window.todo_trust_button.isEnabled())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_prepare_workspace_opens_confirmation_preview_page(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            store.create(
                "准备工作区",
                workspace=TodoWorkspaceHint(apps=["Cursor"], urls=["https://example.com"]),
            )
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window._show_todo_page()
            app.processEvents()
            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            window._workspace_from_selected_todo()
            app.processEvents()

            preview = window.workspace_confirm_text.toPlainText()
            self.assertIs(window.stack.currentWidget(), window.workspace_confirm_page)
            self.assertIn("应用", preview)
            self.assertIn("Cursor", preview)
            self.assertIn("网页", preview)
            self.assertIn("https://example.com", preview)
            self.assertTrue(window.workspace_confirm_reject_button.isEnabled())
            self.assertTrue(window.workspace_confirm_run_button.isEnabled())
            self.assertFalse(window.workspace_confirm_trust_button.isEnabled())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_workspace_confirmation_shows_remedy_buttons_after_failure(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window.stack.setCurrentWidget(window.workspace_confirm_page)
            result = execution_failed(
                ActionStep(action_type=ActionType.OPEN_APP, target="QQ"),
                0,
                "running without window",
                code="APP_PROCESS_RUNNING_NO_WINDOW",
                details={"app_name": "QQ"},
            )
            summary = WorkspaceExecutionSummary(
                todo_id=None,
                trace_id="trace",
                choice=ConfirmationChoice.RUN_ONCE,
                accepted=True,
                status="failed",
                message="没有完成",
                results=[result],
                trusted_keys=[],
                executed_actions=[],
            )

            window._workspace_confirm_execution_finished(summary)
            app.processEvents()

            visible = [button.text() for button in window.workspace_remedy_buttons if button.isVisible()]
            self.assertIn("5秒后再聚焦", visible)
            self.assertIn("可以继续", window.workspace_confirm_text.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_select_path_remedy_returns_to_editor_and_prefills_target(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window._show_workspace_page()
            window.stack.setCurrentWidget(window.workspace_confirm_page)
            window.confirm_return_to_workspace = True
            missing = str(root / "missing.md")
            result = execution_failed(
                ActionStep(action_type=ActionType.OPEN_FILE, target=missing),
                0,
                "file missing",
                code="FILE_NOT_FOUND",
                details={"path": missing},
            )
            summary = WorkspaceExecutionSummary(
                todo_id=None,
                trace_id="trace",
                choice=ConfirmationChoice.RUN_ONCE,
                accepted=True,
                status="failed",
                message="没有完成",
                results=[result],
                trusted_keys=[],
                executed_actions=[],
            )
            window._workspace_confirm_execution_finished(summary)

            window._run_workspace_remedy_index(0)
            app.processEvents()

            self.assertIs(window.stack.currentWidget(), window.workspace_page)
            self.assertEqual(window.workspace_plan_action_type_combo.currentData(), "open_file")
            self.assertEqual(window.workspace_plan_action_target_input.currentText(), missing)
            self.assertIn("重新挑文件", window.workspace_text.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_todo_detail_editor_updates_selected_todo_and_home_status(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            todo = store.create("旧待办", description="旧说明")
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window._show_todo_page()
            app.processEvents()
            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            app.processEvents()

            self.assertEqual(window.todo_input.text(), "旧待办")
            self.assertEqual(window.todo_description_input.text(), "旧说明")

            window.todo_input.setText("新待办")
            window.todo_description_input.setText("新说明")
            window.todo_time_input.setText("30m")
            window.todo_priority_combo.setCurrentIndex(window.todo_priority_combo.findData("urgent"))
            window.important_check.setChecked(True)
            window._save_selected_todo_changes()

            updated = store.get(todo.id)
            self.assertEqual(updated.title, "新待办")
            self.assertEqual(updated.description, "新说明")
            self.assertEqual(updated.priority.value, "urgent")
            self.assertTrue(updated.important)
            self.assertIsNotNone(updated.reminder_at)
            self.assertEqual(window.controller.snapshot().home.urgency.value, "red")
            self.assertIn(shell_text.TODO_CHANGES_SAVED, window.todo_detail.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_cancel_selected_todo_hides_it_without_deleting_record(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            todo = store.create("取消测试")
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window._show_todo_page()
            app.processEvents()
            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()

            window._cancel_selected_todo()

            self.assertEqual(store.get(todo.id).status.value, "cancelled")
            self.assertEqual(window.controller.snapshot().todos, [])
            self.assertEqual(store.list(include_done=True)[0].id, todo.id)
            self.assertIn(shell_text.TODO_CANCELLED, window.todo_detail.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_delete_selected_todo_removes_record_and_clears_detail_state(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            todo = store.create("删除测试", workspace=TodoWorkspaceHint(urls=["https://example.com"]))
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window._show_todo_page()
            app.processEvents()
            list_size = (window.width(), window.height())
            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            app.processEvents()

            self.assertIsNotNone(store.get(todo.id))
            self.assertIs(window.stack.currentWidget(), window.todo_detail_page)
            self.assertIn("删除测试", window.todo_detail.toPlainText())
            self.assertGreater(window.workspace_action_list.count(), 0)
            self.assertNotEqual((window.width(), window.height()), list_size)

            window._delete_selected_todo()
            app.processEvents()

            self.assertIsNone(store.get(todo.id))
            self.assertEqual(window._todo_item_count(), 0)
            self.assertIs(window.stack.currentWidget(), window.todo_page)
            self.assertEqual((window.width(), window.height()), list_size)
            self.assertIn(shell_text.TODO_DELETED, window.todo_detail.toPlainText())
            self.assertIsNone(window.current_suggestion)
            self.assertEqual(window.workspace_action_list.count(), 0)
            self.assertEqual(window.workspace_action_target_input.currentText(), "")
            self.assertEqual(window.todo_input.text(), "")
            self.assertFalse(window.todo_save_button.isEnabled())
            self.assertFalse(window.todo_run_once_button.isEnabled())
            self.assertFalse(window.todo_trust_button.isEnabled())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_delete_then_return_to_menu_and_reenter_todo_keeps_item_deleted(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            legacy_store = TodoStore(root / "data" / "todos.json")
            todo = legacy_store.create("删除后不能复活")
            store = TodoStore(root / "data" / "desktop_assistant.db")
            store._legacy_json_path = root / "data" / "todos.json"
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window._show_todo_page()
            app.processEvents()
            list_size = (window.width(), window.height())
            self.assertEqual(window._todo_item_count(), 1)

            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            app.processEvents()
            detail_size = (window.width(), window.height())
            self.assertNotEqual(detail_size, list_size)

            window._delete_selected_todo()
            app.processEvents()
            self.assertEqual(window._todo_item_count(), 0)
            self.assertEqual((window.width(), window.height()), list_size)
            self.assertIsNone(store.get(todo.id))
            self.assertEqual(legacy_store.list(include_done=True), [])

            window._show_menu()
            app.processEvents()

            window._show_todo_page()
            app.processEvents()
            self.assertEqual((window.width(), window.height()), list_size)
            self.assertEqual(window._todo_item_count(), 0)
            self.assertEqual(store.list(include_done=True), [])
            self.assertEqual(legacy_store.list(include_done=True), [])
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_workspace_execution_result_is_written_back_to_todo(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            todo = store.create("打开资料", workspace=TodoWorkspaceHint(urls=["https://example.com"]))
            controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.controller = controller
            window.show()
            window._show_todo_page()
            app.processEvents()
            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()

            window._workspace_execution_finished(
                WorkspaceExecutionSummary(
                    todo_id=todo.id,
                    trace_id="workspace-test",
                    choice=ConfirmationChoice.RUN_ONCE,
                    accepted=True,
                    status="success",
                    message="opened",
                    results=[],
                    trusted_keys=[],
                    executed_actions=[
                        {
                            "action_type": "open_url",
                            "target": "https://example.com",
                            "status": "success",
                        }
                    ],
                )
            )

            updated = store.get(todo.id)
            self.assertEqual(updated.last_execution.trace_id, "workspace-test")
            self.assertEqual(updated.last_execution.status, "success")
            self.assertEqual(updated.last_execution.executed_actions[0]["target"], "https://example.com")
            self.assertEqual(updated.last_execution.executed_actions[0]["status"], "success")
            self.assertIn("opened", window.todo_detail.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_todo_workspace_actions_can_be_unchecked_and_added(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            store.create(
                "准备资料",
                workspace=TodoWorkspaceHint(apps=["Cursor"], urls=["https://example.com"]),
            )
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window._show_todo_page()
            app.processEvents()
            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()

            self.assertEqual(window.workspace_action_list.count(), 2)
            window.workspace_action_list.item(0).setCheckState(Qt.CheckState.Unchecked)
            window.workspace_action_type_combo.setCurrentText("网页")
            window.workspace_action_target_input.setEditText("https://openai.com")
            window._add_workspace_action()

            edited = window._current_edited_suggestion()
            targets = [step.target for step in edited.plan.steps]
            self.assertNotIn("Cursor", targets)
            self.assertIn("https://example.com", targets)
            self.assertIn("https://openai.com", targets)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_workspace_action_app_target_uses_inventory_dropdown_and_resolution(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.adapters.windows_app_discovery import (
            ApplicationInventory,
            ApplicationInventoryStore,
            DiscoveredApplication,
        )
        from desktop_assistant.ui.shell_window import AssistantShellWindow
        from desktop_assistant.workspace import WorkspaceService, WorkspaceSuggestionBuilder

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            inventory_store = ApplicationInventoryStore(path=root / "app_inventory.json")
            inventory_store.save(
                ApplicationInventory(
                    generated_at="2026-05-01T00:00:00+00:00",
                    applications=[
                        DiscoveredApplication(
                            name="QQ",
                            executable_path="C:\\Apps\\QQ\\QQ.exe",
                            functions=("chat",),
                            source="test",
                        ),
                        DiscoveredApplication(
                            name="Cursor",
                            executable_path="C:\\Apps\\Cursor\\Cursor.exe",
                            functions=("development",),
                            source="test",
                        ),
                    ],
                )
            )
            store = TodoStore(root / "todos.json")
            store.create("准备工作")
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                workspace_service=WorkspaceService(
                    builder=WorkspaceSuggestionBuilder(app_inventory_store=inventory_store)
                ),
            )
            window.show()
            window._show_todo_page()
            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            app.processEvents()

            window.workspace_action_type_combo.setCurrentIndex(window.workspace_action_type_combo.findData("open_app"))
            window._workspace_action_type_changed()
            options = [window.workspace_action_target_input.itemText(index) for index in range(window.workspace_action_target_input.count())]
            self.assertIn("QQ", options)
            self.assertIn("Cursor", options)

            window.workspace_action_target_input.setEditText("qq")
            window._add_workspace_action()

            edited = window._current_edited_suggestion()
            targets = [step.target for step in edited.plan.steps]
            self.assertIn("QQ", targets)
            self.assertNotIn("qq", targets)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_workspace_action_file_and_folder_targets_can_be_browsed(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            store.create("整理资料")
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window._show_todo_page()
            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            app.processEvents()

            selected_file = str(root / "report.md")
            window.workspace_action_type_combo.setCurrentIndex(window.workspace_action_type_combo.findData("open_file"))
            window._workspace_action_type_changed()
            self.assertTrue(window.workspace_action_browse_button.isVisible())
            with patch(
                "desktop_assistant.ui.shell_workspace_target.QFileDialog.getOpenFileName",
                return_value=(selected_file, ""),
            ):
                window._browse_workspace_action_target()
            self.assertEqual(window.workspace_action_target_input.currentText(), selected_file)
            window._add_workspace_action()

            selected_folder = str(root / "docs")
            window.workspace_action_type_combo.setCurrentIndex(window.workspace_action_type_combo.findData("open_folder"))
            window._workspace_action_type_changed()
            with patch(
                "desktop_assistant.ui.shell_workspace_target.QFileDialog.getExistingDirectory",
                return_value=selected_folder,
            ):
                window._browse_workspace_action_target()
            self.assertEqual(window.workspace_action_target_input.currentText(), selected_folder)
            window._add_workspace_action()

            targets = [step.target for step in window._current_edited_suggestion().plan.steps]
            self.assertIn(selected_file, targets)
            self.assertIn(selected_folder, targets)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_todo_workspace_binding_is_saved_from_edited_actions(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            todo = store.create("打开 https://old.example")
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.show()
            window._show_todo_page()
            app.processEvents()
            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            app.processEvents()

            self.assertEqual(window.workspace_action_list.count(), 1)
            window.workspace_action_list.item(0).setCheckState(Qt.CheckState.Unchecked)
            window.workspace_action_type_combo.setCurrentIndex(window.workspace_action_type_combo.findData("open_app"))
            window.workspace_action_target_input.setEditText("Cursor")
            window._add_workspace_action()
            window.workspace_action_type_combo.setCurrentIndex(window.workspace_action_type_combo.findData("open_url"))
            window.workspace_action_target_input.setEditText("https://example.com")
            window._add_workspace_action()
            window.needs_computer_check.setChecked(True)
            window._save_selected_workspace_binding()

            updated = store.get(todo.id)
            self.assertTrue(updated.needs_computer)
            self.assertEqual(updated.workspace.apps, ["Cursor"])
            self.assertEqual(updated.workspace.urls, ["https://example.com"])
            self.assertNotIn("https://old.example", updated.workspace.urls)
            preview = window.controller.workspace_preview_from_todo(todo.id)
            self.assertEqual([step.target for step in preview.plan.steps], ["Cursor", "https://example.com"])
            self.assertIn(shell_text.TODO_WORKSPACE_BINDING_SAVED, window.todo_detail.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_adding_todo_from_shell_accepts_time_and_priority(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.controller = controller
            window.show()
            window._show_todo_page()
            app.processEvents()

            window.todo_input.setText("提交报告")
            window.todo_time_input.setText("30m")
            window.todo_priority_combo.setCurrentText("紧急")
            window._add_todo()

            created = controller.snapshot().todos[0]
            self.assertEqual(created.title, "提交报告")
            self.assertEqual(created.priority.value, "urgent")
            self.assertIsNotNone(created.reminder_at)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_adding_and_editing_todo_task_type_from_shell(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.controller = controller
            window.show()
            window._show_todo_page()
            app.processEvents()

            window.todo_quick_input.setText("daily task")
            window.todo_quick_type_combo.setCurrentIndex(window.todo_quick_type_combo.findData("daily"))
            window._quick_add_todo()
            created = controller.snapshot().todos[0]

            self.assertEqual(created.task_type.value, "daily")
            self.assertIn("daily task", window._todo_item_at(0).text())

            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            window.todo_type_combo.setCurrentIndex(window.todo_type_combo.findData("temporary"))
            window._save_selected_todo_changes()
            updated = controller.get_todo(created.id)

            self.assertEqual(updated.task_type.value, "temporary")
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_completing_daily_todo_keeps_it_visible_as_today_done(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            daily = controller.add_todo("drink water", task_type=TodoTaskType.DAILY)
            temporary = controller.add_todo("buy milk", task_type=TodoTaskType.TEMPORARY)
            window.controller = controller
            window.show()
            window._show_todo_page()
            app.processEvents()

            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            self.assertEqual(window._selected_todo_id(), daily.id)
            window._complete_selected_todo()

            self.assertEqual(window._todo_item_count(), 2)
            self.assertIn("今日已完成", window._todo_item_at(0).text())

            window.todo_list.setCurrentRow(window._todo_actual_row(1))
            self.assertEqual(window._selected_todo_id(), temporary.id)
            window._complete_selected_todo()

            self.assertEqual(window._todo_item_count(), 1)
            self.assertEqual(window._todo_item_at(0).data(Qt.ItemDataRole.UserRole), daily.id)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_daily_todo_can_be_skipped_for_today_from_shell(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            daily = controller.add_todo("stretch", task_type=TodoTaskType.DAILY, reminder_at="2026-05-04T09:00:00+00:00")
            window.controller = controller
            window.show()
            window._show_todo_page()
            app.processEvents()

            window.todo_list.setCurrentRow(window._todo_actual_row(0))
            window._todo_selection_changed()
            window._skip_selected_todo_today()

            updated = controller.get_todo(daily.id)
            logical_today = controller.reminder_settings().logical_date(datetime.now(UTC))
            self.assertEqual(updated.daily_skipped_on, logical_today)
            self.assertIn("已跳过今天", window.todo_detail.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_due_todo_reminder_uses_tray_and_pet_bubble(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            store = TodoStore(root / "todos.json")
            todo = store.create("remind me", reminder_at="2026-05-04T08:00:00+00:00")
            window.controller = AssistantShellController(
                todo_store=store,
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            tray_icon = Mock()
            pet = Mock()
            window.tray_icon = tray_icon
            window.pet_window = pet
            from desktop_assistant.todo.reminders import due_todo_reminders as real_due_todo_reminders

            with patch(
                "desktop_assistant.ui.shell_window.due_todo_reminders",
                lambda todos, **kwargs: real_due_todo_reminders(todos, quiet_hours=None),
            ):
                window._check_due_todo_reminders()

            tray_icon.showMessage.assert_called_once()
            pet.show_reminder_bubble.assert_called_once()
            updated = store.get(todo.id)
            self.assertTrue(updated.last_reminder_key.startswith(f"temporary:{todo.id}:"))
            with patch(
                "desktop_assistant.ui.shell_window.due_todo_reminders",
                lambda todos, **kwargs: real_due_todo_reminders(todos, quiet_hours=None),
            ):
                window._check_due_todo_reminders()
            self.assertEqual(tray_icon.showMessage.call_count, 1)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_todo_page_add_button_creates_visible_item_and_feedback(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QPushButton
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.controller = controller
            window.show()
            window._show_todo_page()
            app.processEvents()

            add_button = next(
                button
                for button in window.todo_page.findChildren(QPushButton)
                if button.text() == shell_text.TODO_ADD
            )
            window.todo_quick_input.setText("按钮添加测试")
            add_button.click()
            app.processEvents()

            self.assertEqual(window._todo_item_count(), 1)
            self.assertIsNotNone(window._todo_item_at(0))
            self.assertEqual(controller.snapshot().todos[0].title, "按钮添加测试")
            self.assertEqual(window.todo_quick_input.text(), "")
            self.assertIn("按钮添加测试", window.todo_feedback_label.text())
            self.assertTrue(window.todo_feedback_label.isVisible())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_todo_page_add_button_shows_feedback_for_empty_input(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QPushButton
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
            )
            window.controller = controller
            window.show()
            window._show_todo_page()
            app.processEvents()

            add_button = next(
                button
                for button in window.todo_page.findChildren(QPushButton)
                if button.text() == shell_text.TODO_ADD
            )
            add_button.click()
            app.processEvents()

            self.assertEqual(window._todo_item_count(), 0)
            self.assertIn(shell_text.TODO_EMPTY_TITLE, window.todo_feedback_label.text())
            self.assertTrue(window.todo_feedback_label.isVisible())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_vague_continue_uses_prediction_context(self) -> None:
        root = _workspace_path()
        try:
            prediction_store = NextActionPredictionStore(root / "prediction.json")
            prediction_store.save(
                NextActionPrediction(
                    suggested_text="继续：desktop_assistant 的 UI 设计",
                    route_hint="continue_work",
                    confidence="medium",
                    source="context_completion",
                )
            )
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=prediction_store,
            )

            route = controller.route_input("继续")

            self.assertEqual(route.route_type, InputRouteType.CONTINUE_WORK)
            self.assertEqual(route.normalized_text, "继续：desktop_assistant 的 UI 设计")
        finally:
            rmtree(root, ignore_errors=True)

    def test_workspace_goal_is_saved_as_pending_draft(self) -> None:
        root = _workspace_path()
        try:
            draft_store = WorkspaceDraftStore(root / "drafts.json")
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                workspace_service=WorkspaceService(draft_store=draft_store),
            )

            suggestion = controller.workspace_from_goal("打开 https://example.com")
            pending = draft_store.latest_pending()

            self.assertTrue(suggestion.has_actions())
            self.assertIsNotNone(pending)
            self.assertEqual(pending.id, suggestion.id)
        finally:
            rmtree(root, ignore_errors=True)

    def test_workspace_refine_keeps_same_pending_draft_id(self) -> None:
        root = _workspace_path()
        try:
            draft_store = WorkspaceDraftStore(root / "drafts.json")
            controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                workspace_service=WorkspaceService(draft_store=draft_store),
            )

            suggestion = controller.workspace_from_goal("打开 https://example.com")
            refined = controller.refine_workspace(suggestion, "再打开 https://openai.com")
            pending = controller.pending_workspace_draft(suggestion.id)

            self.assertEqual(refined.id, suggestion.id)
            self.assertIsNotNone(pending)
            self.assertEqual(pending.id, suggestion.id)
            self.assertEqual(len(pending.plan.steps), 2)
        finally:
            rmtree(root, ignore_errors=True)

    def test_workspace_suggestion_text_is_natural_and_localized(self) -> None:
        from desktop_assistant.ui.shell_workspace_view import workspace_suggestion_text

        suggestion = WorkspaceSuggestion(
            goal="继续 UI 设计",
            title="工作区建议",
            summary="建议执行 2 个动作。",
            plan=ActionPlan(
                plan_name="workspace",
                source="test",
                steps=[
                    ActionStep(action_type=ActionType.OPEN_APP, target="Cursor", reason="open_app"),
                    ActionStep(action_type=ActionType.OPEN_URL, target="https://example.com", reason="open_url"),
                ],
            ),
        )

        rendered = workspace_suggestion_text(suggestion)

        self.assertIn("我建议", rendered)
        self.assertIn("目标：继续 UI 设计", rendered)
        self.assertIn("打开应用：Cursor", rendered)
        self.assertIn("打开网页：https://example.com", rendered)
        self.assertNotIn("open_url ->", rendered)

    def test_workspace_goal_can_enter_confirmation_without_todo(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            draft_store = WorkspaceDraftStore(root / "drafts.json")
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                workspace_service=WorkspaceService(draft_store=draft_store),
            )
            window.show()
            window._show_workspace_page()
            window.workspace_input.setText("打开 https://example.com")
            window._plan_workspace_goal()
            app.processEvents()

            preview = window.workspace_confirm_text.toPlainText()
            self.assertIs(window.stack.currentWidget(), window.workspace_confirm_page)
            self.assertIn("网页", preview)
            self.assertIn("https://example.com", preview)
            self.assertTrue(window.workspace_confirm_run_button.isEnabled())

            window._back_from_workspace_confirmation()
            self.assertIs(window.stack.currentWidget(), window.workspace_page)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_continue_from_menu_confirmation_back_returns_to_menu(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            prediction_store = NextActionPredictionStore(root / "prediction.json")
            prediction_store.save(
                NextActionPrediction(
                    suggested_text="继续：打开 https://example.com",
                    route_hint="continue_work",
                    confidence="high",
                    source="context_completion",
                )
            )
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=prediction_store,
                workspace_service=WorkspaceService(draft_store=WorkspaceDraftStore(root / "drafts.json")),
            )
            window.show()
            window._refresh_home()
            window._show_menu()

            window._continue_from_prediction()
            app.processEvents()

            self.assertIs(window.stack.currentWidget(), window.workspace_confirm_page)
            self.assertIn("https://example.com", window.workspace_confirm_text.toPlainText())

            window._back_from_workspace_confirmation()
            app.processEvents()

            self.assertIs(window.stack.currentWidget(), window.menu_page)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_home_open_command_skips_workspace_editor_when_actions_exist(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                workspace_service=WorkspaceService(draft_store=WorkspaceDraftStore(root / "drafts.json")),
            )
            window.show()
            window._refresh_home()

            window._submit_text("打开 https://example.com", False)
            app.processEvents()

            self.assertIs(window.stack.currentWidget(), window.workspace_confirm_page)
            self.assertIn("https://example.com", window.workspace_confirm_text.toPlainText())
            self.assertTrue(window.workspace_confirm_run_button.isEnabled())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_accepted_pending_workspace_prediction_opens_confirmation(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            draft_store = WorkspaceDraftStore(root / "drafts.json")
            prediction_store = NextActionPredictionStore(root / "prediction.json")
            service = WorkspaceService(draft_store=draft_store)
            suggestion = service.save_draft(service.builder.from_goal("打开 https://example.com"))
            prediction_store.save(
                NextActionPrediction(
                    suggested_text=f"继续确认工作区：{suggestion.title}",
                    route_hint="workspace",
                    confidence="high",
                    source="pending_workspace",
                    target_id=suggestion.id,
                )
            )
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=prediction_store,
                workspace_service=service,
            )
            window.show()
            window._refresh_home()

            window._submit_text("", True)
            app.processEvents()

            self.assertIs(window.stack.currentWidget(), window.workspace_confirm_page)
            self.assertEqual(window.current_suggestion.id, suggestion.id)
            self.assertIn("https://example.com", window.workspace_confirm_text.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_accepted_todo_prediction_opens_workspace_confirmation(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            todo_store = TodoStore(root / "todos.json")
            todo = todo_store.create(
                "准备资料",
                needs_computer=True,
                workspace=TodoWorkspaceHint(urls=["https://example.com"]),
            )
            prediction_store = NextActionPredictionStore(root / "prediction.json")
            prediction_store.save(
                NextActionPrediction(
                    suggested_text=f"为待办准备工作区：{todo.title}",
                    route_hint="todo",
                    confidence="high",
                    source="urgent_todo",
                    target_id=todo.id,
                )
            )
            window.controller = AssistantShellController(
                todo_store=todo_store,
                prediction_store=prediction_store,
                workspace_service=WorkspaceService(draft_store=WorkspaceDraftStore(root / "drafts.json")),
            )
            window.show()
            window._refresh_home()

            window._submit_text("", True)
            app.processEvents()

            self.assertIs(window.stack.currentWidget(), window.workspace_confirm_page)
            self.assertEqual(window.confirm_todo_id, todo.id)
            self.assertIn("https://example.com", window.workspace_confirm_text.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)


class WorkspaceExecuteWorkerTests(unittest.TestCase):
    def test_workspace_worker_executes_confirmed_plan(self) -> None:
        plan = ActionPlan(
            plan_name="workspace",
            source="test",
            steps=[ActionStep(action_type=ActionType.OPEN_URL, target="https://example.com")],
        )
        finished = []
        worker = WorkspaceExecuteWorker(
            plan,
            todo_id="todo-1",
            choice=ConfirmationChoice.RUN_ONCE,
            executor=_FakeWorkspaceExecutor(),
        )
        worker.finished.connect(finished.append)

        worker.run()

        self.assertEqual(len(finished), 1)
        summary = finished[0]
        self.assertTrue(summary.accepted)
        self.assertEqual(summary.status, "success")
        self.assertEqual(summary.todo_id, "todo-1")
        self.assertTrue(summary.trace_id.startswith("workspace-"))
        self.assertEqual(summary.executed_actions[0]["target"], "https://example.com")
        self.assertEqual(summary.executed_actions[0]["status"], "success")

    def test_workspace_worker_records_real_result_statuses(self) -> None:
        plan = ActionPlan(
            plan_name="workspace",
            source="test",
            steps=[
                ActionStep(action_type=ActionType.OPEN_URL, target="https://example.com"),
                ActionStep(action_type=ActionType.OPEN_APP, target="QQ"),
            ],
        )
        finished = []
        worker = WorkspaceExecuteWorker(
            plan,
            todo_id="todo-1",
            choice=ConfirmationChoice.RUN_ONCE,
            executor=_MixedWorkspaceExecutor(),
        )
        worker.finished.connect(finished.append)

        worker.run()

        summary = finished[0]
        self.assertEqual(summary.status, "partial")
        self.assertEqual(summary.executed_actions[0]["status"], "success")
        self.assertEqual(summary.executed_actions[1]["status"], "failed")
        self.assertIn("failed", summary.executed_actions[1]["message"].lower())


class _FakeWorkspaceExecutor:
    def execute(self, action: ActionStep, step_index: int, trace_id: str):
        return execution_success(action, step_index, f"[{trace_id}] ok")


class _MixedWorkspaceExecutor:
    def execute(self, action: ActionStep, step_index: int, trace_id: str):
        if step_index == 0:
            return execution_success(action, step_index, f"[{trace_id}] ok")
        return execution_failed(action, step_index, f"[{trace_id}] failed", code="APP_NOT_IN_INVENTORY")


if __name__ == "__main__":
    unittest.main()
