from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QElapsedTimer, QEvent, QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from ..ui_state import AssistantUiStateStore
from .native_window import remove_native_window_frame
from .shell_orb import LivingOrb, PET_WINDOW_HEIGHT, PET_WINDOW_WIDTH
from .shell_styles import shell_style


PET_MENU_TITLE = "暮蝶：要我做什么？"
PET_MENU_SHOW_PANEL_TEXT = "打开面板"
PET_MENU_QUIT_TEXT = "退出应用"
PET_HEAD_OFFSET = QPoint(PET_WINDOW_WIDTH // 2, 48)
PET_MENU_REMINDER_SETTINGS_TEXT = "提醒设置"
BUBBLE_COLUMN_WIDTH = 264
BUBBLE_CONNECTOR_WIDTH = 96
BUBBLE_MENU_WIDTH = BUBBLE_COLUMN_WIDTH + BUBBLE_CONNECTOR_WIDTH
BUBBLE_REVEAL_DURATION_MS = 520
BUBBLE_REVEAL_STAGGER_MS = 95
REMINDER_BUBBLE_AUTO_CLOSE_MS = 6500


class PetBubbleLabel(QLabel):
    """A standalone prompt bubble so the menu never reads as one large panel."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._tail_side = "right"
        self.setObjectName("petBubbleTitle")
        self.setWordWrap(True)
        self._bubble_width = 218
        self._reveal_progress = 0.0
        self.setFixedSize(self._bubble_width, 50)
        self.setStyleSheet("background: transparent; border: none; color: transparent;")

    def set_tail_side(self, side: str) -> None:
        self._tail_side = "left" if side == "left" else "right"
        self.update()

    def set_reveal_progress(self, progress: float) -> None:
        self._reveal_progress = max(0.0, min(1.0, progress))
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        if self._reveal_progress <= 0.34:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        body_progress = _ease_out((self._reveal_progress - 0.34) / 0.66)
        bubble_box = self._bubble_box(body_progress)
        _paint_speech_bubble(
            painter,
            bubble_box,
            self._tail_side,
            (QColor(43, 55, 88, 246), QColor(91, 82, 132, 246), QColor(66, 74, 115, 246)),
            QColor(180, 211, 255, 150),
            radius=17,
        )
        if body_progress > 0.72:
            painter.setPen(QColor(248, 251, 255, round(255 * min(1.0, (body_progress - 0.72) / 0.28))))
            font = painter.font()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            text_rect = _bubble_text_rect(bubble_box, self._tail_side)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, self.text())
        painter.end()

    def tail_point(self) -> QPointF:
        box = self._bubble_box(max(0.18, _ease_out((self._reveal_progress - 0.34) / 0.66)))
        return _tail_tip(box, self._tail_side)

    def visual_width(self) -> int:
        return self._bubble_width

    def _bubble_box(self, progress: float) -> QRectF:
        progress = max(0.0, min(1.0, progress))
        width = max(34.0, (self.width() - 4) * (0.24 + (0.76 * progress)))
        if self._tail_side == "left":
            x = 2
        else:
            x = self.width() - width - 2
        return QRectF(x, 2, width, self.height() - 4)


class PetBubbleButton(QPushButton):
    """A selectable user reply bubble, visually distinct from the pet's speech."""

    def __init__(self, text: str, *, accent: bool = False) -> None:
        super().__init__(text)
        self._tail_side = "right"
        self._accent = accent
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("petBubbleQuit" if accent else "petBubbleOption")
        self._bubble_width = _bubble_width_for_text(text, accent=accent)
        self._reveal_progress = 0.0
        self.setFixedSize(self._bubble_width, 48)
        self.setMouseTracking(True)
        self.setStyleSheet("background: transparent; border: none; color: transparent;")

    def set_tail_side(self, side: str) -> None:
        self._tail_side = "left" if side == "left" else "right"
        self.update()

    def set_reveal_progress(self, progress: float) -> None:
        self._reveal_progress = max(0.0, min(1.0, progress))
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        if self._reveal_progress <= 0.34:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        body_progress = _ease_out((self._reveal_progress - 0.34) / 0.66)
        bubble_box = self._bubble_box(body_progress)
        self._paint_bubble(painter, bubble_box, self.underMouse())
        if body_progress > 0.68:
            painter.setPen(self._text_color(body_progress))
            font = painter.font()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(_bubble_text_rect(bubble_box, self._tail_side), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        painter.end()

    def hitButton(self, pos) -> bool:  # type: ignore[no-untyped-def]
        return self._bubble_box(1.0).contains(QPointF(pos))

    def tail_point(self) -> QPointF:
        box = self._bubble_box(max(0.18, _ease_out((self._reveal_progress - 0.34) / 0.66)))
        return _tail_tip(box, self._tail_side)

    def visual_width(self) -> int:
        return self._bubble_width

    def _bubble_box(self, progress: float) -> QRectF:
        progress = max(0.0, min(1.0, progress))
        width = max(34.0, (self.width() - 4) * (0.24 + (0.76 * progress)))
        if self._tail_side == "left":
            x = 2
        else:
            x = self.width() - width - 2
        return QRectF(x, 2, width, self.height() - 4)

    def _paint_bubble(self, painter: QPainter, bubble_box: QRectF, hovered: bool) -> None:
        if self._accent:
            start = QColor(255, 250, 252, 252)
            mid = QColor(255, 242, 248, 250)
            end = QColor(255, 238, 242, 248)
            border = QColor(247, 157, 199, 210)
        else:
            start = QColor(255, 255, 255, 252)
            mid = QColor(248, 252, 255, 250)
            end = QColor(245, 248, 255, 248)
            border = QColor(180, 211, 255, 205)
        if hovered:
            start = QColor(255, 255, 255, 255)
            mid = QColor(255, 250, 254, 254)
            end = QColor(239, 247, 255, 252)
            border = QColor(247, 177, 220, 225)
        _paint_speech_bubble(painter, bubble_box, self._tail_side, (start, mid, end), border, radius=18)

    def _text_color(self, body_progress: float) -> QColor:
        alpha = round(255 * min(1.0, (body_progress - 0.68) / 0.32))
        if self._accent:
            return QColor(126, 54, 91, alpha)
        return QColor(44, 55, 88, alpha)


def _paint_speech_bubble(
    painter: QPainter,
    bubble_box: QRectF,
    tail_side: str,
    colors: tuple[QColor, QColor, QColor],
    border: QColor,
    *,
    radius: int,
) -> None:  # type: ignore[no-untyped-def]
    del tail_side
    body = QRectF(bubble_box)

    bubble_gradient = QLinearGradient(body.topLeft(), body.bottomRight())
    bubble_gradient.setColorAt(0.0, colors[0])
    bubble_gradient.setColorAt(0.55, colors[1])
    bubble_gradient.setColorAt(1.0, colors[2])

    painter.setPen(QPen(border, 1))
    painter.setBrush(bubble_gradient)
    painter.drawRoundedRect(body, radius, radius)


def _tail_tip(bubble_box: QRectF, tail_side: str) -> QPointF:
    if tail_side == "left":
        return QPointF(bubble_box.left(), bubble_box.center().y())
    return QPointF(bubble_box.right(), bubble_box.center().y())


def _bubble_text_rect(bubble_box: QRectF, tail_side: str) -> QRectF:
    if tail_side == "left":
        return QRectF(bubble_box.left() + 16, bubble_box.top() + 2, bubble_box.width() - 28, bubble_box.height() - 4)
    return QRectF(bubble_box.left() + 14, bubble_box.top() + 2, bubble_box.width() - 28, bubble_box.height() - 4)


def _ease_out(progress: float) -> float:
    value = max(0.0, min(1.0, progress))
    return 1.0 - ((1.0 - value) ** 3)


def _quadratic_point(start: QPointF, control: QPointF, end: QPointF, progress: float) -> QPointF:
    t = max(0.0, min(1.0, progress))
    left = (1.0 - t) * (1.0 - t)
    middle = 2.0 * (1.0 - t) * t
    right = t * t
    return QPointF(
        (left * start.x()) + (middle * control.x()) + (right * end.x()),
        (left * start.y()) + (middle * control.y()) + (right * end.y()),
    )


def _bubble_width_for_text(text: str, *, accent: bool) -> int:
    return min(222, max(156 if accent else 174, (len(text) * 15) + 92))


class PetBubbleMenu(QWidget):
    """Small chat-bubble action menu shown from the desktop pet."""

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        hidden: bool,
        on_show_panel: Callable[[], None],
        on_reminder_settings: Callable[[], None],
        on_quit: Callable[[], None],
        on_dismiss: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        del hidden
        self._tail_side = "right"
        self._on_show_panel = on_show_panel
        self._on_reminder_settings = on_reminder_settings
        self._on_quit = on_quit
        self._on_dismiss = on_dismiss
        self._source_point = QPointF(0, 0)
        self._birth_timer = QElapsedTimer()
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(16)
        self._animation_timer.timeout.connect(self._advance_birth_animation)
        if parent is None:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.NoDropShadowWindowHint
            )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("PetBubbleMenu { background: transparent; border: none; }")
        self.setFixedWidth(BUBBLE_MENU_WIDTH)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._layout.setSpacing(8)

        title = PetBubbleLabel(PET_MENU_TITLE)
        self._layout.addWidget(title)

        self._add_option(PET_MENU_SHOW_PANEL_TEXT, self._on_show_panel)
        self._add_option(PET_MENU_REMINDER_SETTINGS_TEXT, self._on_reminder_settings)
        self._add_option(PET_MENU_QUIT_TEXT, self._on_quit, quit_option=True)
        self._apply_bubble_alignment()
        self._start_birth_animation()

    def set_source_point(self, point: QPointF) -> None:
        self._source_point = point
        self.update()

    def set_tail_side(self, side: str) -> None:
        self._tail_side = "left" if side == "left" else "right"
        self._apply_bubble_alignment()
        self.update()

    def _apply_bubble_alignment(self) -> None:
        alignment = Qt.AlignmentFlag.AlignLeft if self._tail_side == "left" else Qt.AlignmentFlag.AlignRight
        for bubble in [*self.findChildren(PetBubbleLabel), *self.findChildren(PetBubbleButton)]:
            bubble.set_tail_side(self._tail_side)
            self._layout.setAlignment(bubble, alignment)
        if self._tail_side == "left":
            self._layout.setContentsMargins(BUBBLE_CONNECTOR_WIDTH, 4, 0, 4)
        else:
            self._layout.setContentsMargins(0, 4, BUBBLE_CONNECTOR_WIDTH, 4)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        if self.parentWidget() is not None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        title = self._title_bubble()
        if title is not None:
            self._paint_birth_dots(painter, title, 0)
        painter.end()

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton and self.parentWidget() is not None:
            parent = self.parentWidget()
            if hasattr(parent, "dismiss_bubble_menu"):
                parent.dismiss_bubble_menu()
                event.accept()
                return
        super().mousePressEvent(event)

    def _add_option(self, text: str, callback: Callable[[], None], *, quit_option: bool = False) -> None:
        button = PetBubbleButton(text, accent=quit_option)
        button.clicked.connect(lambda checked=False, selected=callback: self._choose(selected))
        self._layout.addWidget(button)

    def _start_birth_animation(self) -> None:
        for bubble in self._birth_bubbles():
            bubble.set_reveal_progress(0.0)
        self._birth_timer.start()
        self._animation_timer.start()

    def _advance_birth_animation(self) -> None:
        elapsed = self._birth_timer.elapsed()
        bubbles = self._birth_bubbles()
        for index, bubble in enumerate(bubbles):
            progress = (elapsed - (index * BUBBLE_REVEAL_STAGGER_MS)) / BUBBLE_REVEAL_DURATION_MS
            bubble.set_reveal_progress(progress)
        if elapsed > BUBBLE_REVEAL_DURATION_MS + ((len(bubbles) - 1) * BUBBLE_REVEAL_STAGGER_MS):
            self._animation_timer.stop()
            for bubble in bubbles:
                bubble.set_reveal_progress(1.0)
        self.update()
        if self.parentWidget() is not None:
            self.parentWidget().update()

    def _birth_bubbles(self) -> list[PetBubbleLabel | PetBubbleButton]:
        return [*self.findChildren(PetBubbleLabel), *self.findChildren(PetBubbleButton)]

    def _title_bubble(self) -> PetBubbleLabel | None:
        labels = self.findChildren(PetBubbleLabel)
        return labels[0] if labels else None

    def _paint_birth_dots(self, painter: QPainter, bubble: PetBubbleLabel | PetBubbleButton, index: int) -> None:
        progress = bubble._reveal_progress  # The menu orchestrates its child bubble birth animation.
        if progress <= 0.0 or progress >= 0.72:
            return
        target_x = bubble.width() - 2 if self._tail_side == "right" else 2
        local_target = bubble.mapTo(self, QPoint(target_x, round(bubble.height() / 2)))
        target = QPointF(local_target)
        source = self._source_point
        curve = QPointF((source.x() + target.x()) / 2, min(source.y(), target.y()) - 18 - (index * 5))
        first_progress = _ease_out(min(1.0, progress / 0.42))
        second_progress = _ease_out(min(1.0, max(0.0, (progress - 0.16) / 0.46)))
        first = _quadratic_point(source, curve, target, first_progress * 0.52)
        second = _quadratic_point(source, curve, target, 0.34 + (second_progress * 0.38))
        painter.setBrush(QColor(180, 211, 255, round(190 * (1.0 - max(0.0, progress - 0.42)))))
        painter.drawEllipse(first, 4.2, 4.2)
        painter.setBrush(QColor(247, 177, 220, round(210 * (1.0 - max(0.0, progress - 0.5)))))
        painter.drawEllipse(second, 6.2, 6.2)

    def _choose(self, callback: Callable[[], None]) -> None:
        self.close()
        callback()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        callback = self._on_dismiss
        self._on_dismiss = None
        if callback is not None:
            callback()
        super().closeEvent(event)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        if self.isWindow():
            remove_native_window_frame(self)

    def focusOutEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.isWindow() and self.isVisible():
            self.close()
        super().focusOutEvent(event)


class PetReminderBubble(QWidget):
    """A reminder: pet speech on top, optional user reply bubbles below."""

    def __init__(
        self,
        message: str,
        *,
        parent: QWidget,
        actions: list[tuple[str, Callable[[], None]]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._tail_side = "right"
        self._source_point = QPointF(0, 0)
        self._label = PetBubbleLabel(message)
        self._label.setFixedSize(min(252, max(200, len(message) * 11 + 48)), 58)
        self._action_buttons: list[PetBubbleButton] = []
        self._birth_timer = QElapsedTimer()
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(16)
        self._animation_timer.timeout.connect(self._advance_birth_animation)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("PetReminderBubble { background: transparent; border: none; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)
        layout.addWidget(self._label)
        for text, callback in actions or []:
            button = PetBubbleButton(text)
            button.clicked.connect(lambda checked=False, selected=callback: self._choose(selected))
            self._action_buttons.append(button)
            layout.addWidget(button)
        self.setFixedWidth(BUBBLE_MENU_WIDTH)
        self.adjustSize()
        self._start_birth_animation()

    def set_source_point(self, point: QPointF) -> None:
        self._source_point = point
        self.update()

    def set_tail_side(self, side: str) -> None:
        self._tail_side = "left" if side == "left" else "right"
        alignment = Qt.AlignmentFlag.AlignLeft if self._tail_side == "left" else Qt.AlignmentFlag.AlignRight
        for bubble in self._birth_bubbles():
            bubble.set_tail_side(self._tail_side)
            self.layout().setAlignment(bubble, alignment)
        if self._tail_side == "left":
            self.layout().setContentsMargins(BUBBLE_CONNECTOR_WIDTH, 4, 0, 4)
        else:
            self.layout().setContentsMargins(0, 4, BUBBLE_CONNECTOR_WIDTH, 4)
        self.update()

    def bubble_label(self) -> PetBubbleLabel:
        return self._label

    def action_buttons(self) -> list[PetBubbleButton]:
        return list(self._action_buttons)

    def _start_birth_animation(self) -> None:
        for bubble in self._birth_bubbles():
            bubble.set_reveal_progress(0.0)
        self._birth_timer.start()
        self._animation_timer.start()

    def _advance_birth_animation(self) -> None:
        elapsed = self._birth_timer.elapsed()
        bubbles = self._birth_bubbles()
        for index, bubble in enumerate(bubbles):
            progress = (elapsed - (index * BUBBLE_REVEAL_STAGGER_MS)) / BUBBLE_REVEAL_DURATION_MS
            bubble.set_reveal_progress(progress)
        if elapsed > BUBBLE_REVEAL_DURATION_MS + ((len(bubbles) - 1) * BUBBLE_REVEAL_STAGGER_MS):
            self._animation_timer.stop()
            for bubble in bubbles:
                bubble.set_reveal_progress(1.0)
        self.update()
        if self.parentWidget() is not None:
            self.parentWidget().update()

    def _birth_bubbles(self) -> list[PetBubbleLabel | PetBubbleButton]:
        return [self._label, *self._action_buttons]

    def _choose(self, callback: Callable[[], None]) -> None:
        parent = self.parentWidget()
        if parent is not None and hasattr(parent, "dismiss_reminder_bubble"):
            parent.dismiss_reminder_bubble()
        callback()


class DesktopPetWindow(QWidget):
    """Always-on-top pet window that can summon the assistant panel."""

    def __init__(
        self,
        *,
        state_store: AssistantUiStateStore | None = None,
        on_activate: Callable[["DesktopPetWindow"], None] | None = None,
        on_reminder_settings: Callable[["DesktopPetWindow"], None] | None = None,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.state_store = state_store or AssistantUiStateStore()
        self.on_activate = on_activate
        self.on_reminder_settings = on_reminder_settings
        self.on_quit = on_quit
        self.drag_position: QPoint | None = None
        self._drag_has_mouse_grab = False
        self._last_drag_global_pos: QPoint | None = None
        self.bubble_menu: PetBubbleMenu | None = None
        self.reminder_bubble: PetReminderBubble | None = None
        self._reminder_close_timer = QTimer(self)
        self._reminder_close_timer.setSingleShot(True)
        self._reminder_close_timer.timeout.connect(self.dismiss_reminder_bubble)
        self._right_click_timer = QTimer(self)
        self._right_click_timer.setSingleShot(True)
        self._right_click_timer.timeout.connect(self._complete_right_click)
        self._pending_right_click_global_pos: QPoint | None = None
        self._pet_offset = QPoint(0, 0)
        self._bubble_source_point = QPointF(0, 0)
        self.pet = LivingOrb()
        self.pet.setParent(self)
        self.pet.setGeometry(0, 0, PET_WINDOW_WIDTH, PET_WINDOW_HEIGHT)
        self.pet.installEventFilter(self)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFixedSize(PET_WINDOW_WIDTH, PET_WINDOW_HEIGHT)
        self.setStyleSheet(shell_style("#2E7D5B", orb=True))
        self._restore_position()

    def set_status_color(self, color: str) -> None:
        self.pet.set_color(color)
        self.setStyleSheet(shell_style(color, orb=True))

    def set_hidden_mode(self, hidden: bool) -> None:
        self.pet.set_hidden_mode(hidden)
        self.setWindowOpacity(0.24 if hidden else 0.92)

    def play_pet_action(self, state: str) -> None:
        self.pet.play_once(state)

    def hold_pet_state(self, state: str) -> None:
        self.pet.hold_state(state)

    def release_pet_hold(self) -> None:
        self.pet.release_hold()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self.bubble_menu is None and self.reminder_bubble is None:
            painter.end()
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.bubble_menu is not None:
            title = self.bubble_menu._title_bubble()
            if title is not None:
                self._paint_embedded_birth_dots(painter, title, 0)
        if self.reminder_bubble is not None:
            self._paint_embedded_birth_dots(painter, self.reminder_bubble.bubble_label(), 0)
        painter.end()

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if watched is self.pet:
            if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
                if self.on_activate is not None:
                    self.on_activate(self)
                event.accept()
                return True
            if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.RightButton:
                self._cancel_pending_right_click()
                self._show_bubble_menu(event.globalPosition().toPoint())
                event.accept()
                return True
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.RightButton:
                self._schedule_right_click_toggle(event.globalPosition().toPoint())
                event.accept()
                return True
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                if self.dismiss_bubble_menu() or self.dismiss_reminder_bubble():
                    self._start_drag(event.globalPosition().toPoint())
                    event.accept()
                    return True
                self._start_drag(event.globalPosition().toPoint())
                return False
            if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
                if self._move_drag(event.globalPosition().toPoint()):
                    return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                self._finish_drag()
                return False
        return super().eventFilter(watched, event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton and self.on_activate is not None:
            self.on_activate(self)
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel_pending_right_click()
            self._show_bubble_menu(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.buttons() & Qt.MouseButton.LeftButton and self._move_drag(event.globalPosition().toPoint()):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._finish_drag()
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        # Right-click is handled as single-click toggle or double-click menu.
        # Suppress Qt's default context-menu event so a single click never opens the menu.
        event.accept()

    def _show_bubble_menu(self, global_pos: QPoint) -> None:
        self.dismiss_reminder_bubble()
        if self.bubble_menu is not None:
            self.dismiss_bubble_menu()
        self.setUpdatesEnabled(False)
        self.pet.setVisible(False)
        tail_side = self._expand_for_bubble_menu(global_pos)
        self.bubble_menu = PetBubbleMenu(
            parent=self,
            hidden=self.state_store.load().orb_hidden,
            on_show_panel=self._activate_from_menu,
            on_reminder_settings=self._open_reminder_settings_from_menu,
            on_quit=self.quit_application,
            on_dismiss=self._clear_bubble_menu,
        )
        self.bubble_menu.adjustSize()
        self.bubble_menu.set_tail_side(tail_side)
        menu_pos = self._bubble_menu_local_position(tail_side)
        self.bubble_menu.move(menu_pos)
        self._bubble_source_point = QPointF(self._pet_offset + PET_HEAD_OFFSET)
        self.bubble_menu.set_source_point(self._bubble_source_point - QPointF(menu_pos))
        self.bubble_menu.show()
        self.bubble_menu.raise_()
        self.pet.setVisible(True)
        self.pet.raise_()
        self.setUpdatesEnabled(True)
        self.repaint()

    def show_reminder_bubble(self, message: str, actions: list[tuple[str, Callable[[], None]]] | None = None) -> None:
        self.dismiss_bubble_menu()
        self.dismiss_reminder_bubble()
        self.setUpdatesEnabled(False)
        self.pet.setVisible(False)
        reminder_actions = actions if actions is not None else [
            ("打开面板", self._activate_from_reminder),
            ("知道了", self.dismiss_reminder_bubble),
        ]
        bubble_height = max(226, 74 + (len(reminder_actions) * 56))
        tail_side = self._expand_for_bubble(self.mapToGlobal(self._pet_offset), bubble_height=bubble_height)
        self.reminder_bubble = PetReminderBubble(message, parent=self, actions=reminder_actions)
        self.reminder_bubble.set_tail_side(tail_side)
        menu_pos = self._bubble_menu_local_position(tail_side)
        self.reminder_bubble.move(menu_pos)
        self._bubble_source_point = QPointF(self._pet_offset + PET_HEAD_OFFSET)
        self.reminder_bubble.set_source_point(self._bubble_source_point - QPointF(menu_pos))
        self.reminder_bubble.show()
        self.reminder_bubble.raise_()
        self.pet.setVisible(True)
        self.pet.raise_()
        self.setUpdatesEnabled(True)
        self.play_pet_action("waving")
        self._reminder_close_timer.start(REMINDER_BUBBLE_AUTO_CLOSE_MS)
        self.repaint()

    def _expand_for_bubble_menu(self, global_pos: QPoint) -> str:
        return self._expand_for_bubble(global_pos, bubble_height=226)

    def _expand_for_bubble(self, global_pos: QPoint, *, bubble_height: int) -> str:
        screen = QApplication.screenAt(global_pos) or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        pet_global = self.mapToGlobal(self._pet_offset)
        margin = 8
        use_left = pet_global.x() - (BUBBLE_MENU_WIDTH - BUBBLE_CONNECTOR_WIDTH) >= available.left() + margin
        tail_side = "right" if use_left else "left"
        if tail_side == "right":
            new_x = pet_global.x() - BUBBLE_MENU_WIDTH
            self._pet_offset = QPoint(BUBBLE_MENU_WIDTH, 0)
        else:
            new_x = pet_global.x()
            self._pet_offset = QPoint(0, 0)
        new_y = min(max(pet_global.y(), available.top() + margin), available.bottom() - max(PET_WINDOW_HEIGHT, bubble_height) - margin)
        target_width = BUBBLE_MENU_WIDTH + PET_WINDOW_WIDTH
        target_height = max(PET_WINDOW_HEIGHT, bubble_height)
        self.setFixedSize(target_width, target_height)
        self.move(new_x, new_y)
        self.pet.setGeometry(self._pet_offset.x(), self._pet_offset.y(), PET_WINDOW_WIDTH, PET_WINDOW_HEIGHT)
        self.clearMask()
        self.update()
        return tail_side

    def _bubble_menu_local_position(self, tail_side: str) -> QPoint:
        if tail_side == "right":
            return QPoint(0, 4)
        return QPoint(PET_WINDOW_WIDTH, 4)

    def _collapse_after_bubble_menu(self) -> None:
        self.setUpdatesEnabled(False)
        self.pet.setVisible(False)
        pet_global = self.mapToGlobal(self._pet_offset)
        self._pet_offset = QPoint(0, 0)
        self.setGeometry(pet_global.x(), pet_global.y(), PET_WINDOW_WIDTH, PET_WINDOW_HEIGHT)
        self.setFixedSize(PET_WINDOW_WIDTH, PET_WINDOW_HEIGHT)
        self.pet.setGeometry(0, 0, PET_WINDOW_WIDTH, PET_WINDOW_HEIGHT)
        self.pet.setVisible(True)
        self.setUpdatesEnabled(True)
        self.repaint()

    def _activate_from_menu(self) -> None:
        if self.on_activate is not None:
            self.on_activate(self)

    def _open_reminder_settings_from_menu(self) -> None:
        if self.on_reminder_settings is not None:
            self.on_reminder_settings(self)
            return
        self._activate_from_menu()

    def _activate_from_reminder(self) -> None:
        self.dismiss_reminder_bubble()
        self._activate_from_menu()

    def dismiss_bubble_menu(self) -> bool:
        if self.bubble_menu is None:
            return False
        menu = self.bubble_menu
        self.bubble_menu = None
        menu._on_dismiss = None
        menu.close()
        self._collapse_after_bubble_menu()
        return True

    def dismiss_reminder_bubble(self) -> bool:
        if self.reminder_bubble is None:
            return False
        bubble = self.reminder_bubble
        self.reminder_bubble = None
        bubble.close()
        if self.bubble_menu is None:
            self._collapse_after_bubble_menu()
        return True

    def _clear_bubble_menu(self) -> None:
        self.bubble_menu = None
        if self.width() != PET_WINDOW_WIDTH or self.height() != PET_WINDOW_HEIGHT:
            self._collapse_after_bubble_menu()
        self.update()

    def _paint_embedded_birth_dots(self, painter: QPainter, bubble: PetBubbleLabel | PetBubbleButton, index: int) -> None:
        progress = bubble._reveal_progress
        if progress <= 0.0 or progress >= 0.72:
            return
        tail_side = "right"
        if self.bubble_menu is not None:
            tail_side = self.bubble_menu._tail_side
        elif self.reminder_bubble is not None:
            tail_side = self.reminder_bubble._tail_side
        target_x = bubble.width() - 2 if tail_side == "right" else 2
        target_local = bubble.mapTo(self, QPoint(target_x, round(bubble.height() / 2)))
        target = QPointF(target_local)
        source = self._bubble_source_point
        curve = QPointF((source.x() + target.x()) / 2, min(source.y(), target.y()) - 18 - (index * 5))
        first_progress = _ease_out(min(1.0, progress / 0.42))
        second_progress = _ease_out(min(1.0, max(0.0, (progress - 0.16) / 0.46)))
        first = _quadratic_point(source, curve, target, first_progress * 0.52)
        second = _quadratic_point(source, curve, target, 0.34 + (second_progress * 0.38))
        painter.setBrush(QColor(180, 211, 255, round(190 * (1.0 - max(0.0, progress - 0.42)))))
        painter.drawEllipse(first, 4.2, 4.2)
        painter.setBrush(QColor(247, 177, 220, round(210 * (1.0 - max(0.0, progress - 0.5)))))
        painter.drawEllipse(second, 6.2, 6.2)

    def toggle_hidden_mode(self) -> None:
        hidden = not self.state_store.load().orb_hidden
        state = self.state_store.update_orb(x=self.x(), y=self.y(), hidden=hidden)
        self.set_hidden_mode(state.orb_hidden)

    def _schedule_right_click_toggle(self, global_pos: QPoint) -> None:
        self._pending_right_click_global_pos = QPoint(global_pos)
        self._right_click_timer.start(max(1, QApplication.doubleClickInterval()))

    def _cancel_pending_right_click(self) -> None:
        self._pending_right_click_global_pos = None
        if self._right_click_timer.isActive():
            self._right_click_timer.stop()

    def _complete_right_click(self) -> None:
        if self._pending_right_click_global_pos is None:
            return
        self._pending_right_click_global_pos = None
        self.toggle_hidden_mode()

    def quit_application(self) -> None:
        if self.on_quit is not None:
            self.on_quit()
            return
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        remove_native_window_frame(self)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._finish_drag()
        self.dismiss_bubble_menu()
        self.dismiss_reminder_bubble()
        super().closeEvent(event)

    def _restore_position(self) -> None:
        state = self.state_store.load()
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else self.geometry()
        x = state.orb.x if state.orb.x else available.right() - PET_WINDOW_WIDTH - 22
        y = state.orb.y if state.orb.y else available.top() + 22
        x = min(max(x, available.left()), available.right() - PET_WINDOW_WIDTH)
        y = min(max(y, available.top()), available.bottom() - PET_WINDOW_HEIGHT)
        self.move(x, y)
        self.set_hidden_mode(state.orb_hidden)

    def _start_drag(self, global_pos: QPoint) -> None:
        self.drag_position = global_pos - self.mapToGlobal(self._pet_offset)
        self._last_drag_global_pos = global_pos
        self.pet.hold_drag_state("jumping")
        self.grabMouse()
        self._drag_has_mouse_grab = True
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _move_drag(self, global_pos: QPoint) -> bool:
        if self.drag_position is None:
            return False
        self._update_drag_animation(global_pos)
        self.move(global_pos - self.drag_position - self._pet_offset)
        return True

    def _finish_drag(self) -> None:
        if self.drag_position is None:
            if self._drag_has_mouse_grab:
                self.releaseMouse()
                self._drag_has_mouse_grab = False
                self.unsetCursor()
            self.pet.release_drag_state()
            self._last_drag_global_pos = None
            return
        self.drag_position = None
        if self._drag_has_mouse_grab:
            self.releaseMouse()
            self._drag_has_mouse_grab = False
        self.unsetCursor()
        self.pet.release_drag_state()
        self._last_drag_global_pos = None
        self.pet.play_once("jumping")
        self.state_store.update_orb(x=self.x(), y=self.y())

    def _update_drag_animation(self, global_pos: QPoint) -> None:
        previous = self._last_drag_global_pos
        self._last_drag_global_pos = global_pos
        if previous is None:
            return
        delta_x = global_pos.x() - previous.x()
        if abs(delta_x) < 3:
            return
        self.pet.hold_drag_state("running-right" if delta_x > 0 else "running-left")
