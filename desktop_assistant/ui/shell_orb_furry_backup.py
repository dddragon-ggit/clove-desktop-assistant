from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


ORB_ORANGE = QColor("#F59E0B")
ORB_GLOW = QColor("#FBBF24")
ORB_FUR = QColor("#F97316")
ORB_FUR_DARK = QColor("#D97706")
ORB_SHADOW = QColor("#7C2D12")
ORB_EYE = QColor("#24140B")
ORB_EYE_SOFT = QColor("#5A3215")
ARTBOARD_SIZE = 180


class LivingOrb(QWidget):
    """Soft orange furry companion orb with two eyes."""

    def __init__(self) -> None:
        super().__init__()
        self._phase = 0.0
        self._tick = 0
        self._hidden = False
        self.setMinimumSize(72, 72)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

    def set_color(self, value: str) -> None:
        del value

    def set_hidden_mode(self, hidden: bool) -> None:
        self._hidden = hidden
        self.update()

    def _advance(self) -> None:
        self._tick += 1
        self._phase = (self._phase + 0.018) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        artboard = QImage(ARTBOARD_SIZE, ARTBOARD_SIZE, QImage.Format.Format_ARGB32_Premultiplied)
        artboard.fill(Qt.GlobalColor.transparent)
        alpha_scale = 0.42 if self._hidden else 1.0
        painter = QPainter(artboard)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_orb(painter, QRectF(0, 0, ARTBOARD_SIZE, ARTBOARD_SIZE), alpha_scale)
        painter.end()

        output = QPainter(self)
        output.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        output.drawImage(QRectF(self.rect()), artboard)
        output.end()

    def _paint_orb(self, painter: QPainter, canvas: QRectF, alpha_scale: float) -> None:
        breath = math.sin(self._phase * math.tau)
        body = canvas.adjusted(11, 10, -11, -10)
        body = body.adjusted(-breath * 0.55, breath * 0.45, breath * 0.55, -breath * 0.45)

        self._draw_shadow(painter, body, alpha_scale)
        self._draw_fur_halo(painter, body, alpha_scale)
        self._draw_body(painter, body, alpha_scale)
        self._draw_inner_fur(painter, body, alpha_scale)
        self._draw_eyes(painter, body, alpha_scale)

    def _draw_shadow(self, painter: QPainter, body: QRectF, alpha_scale: float) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ORB_SHADOW.red(), ORB_SHADOW.green(), ORB_SHADOW.blue(), int(30 * alpha_scale)))
        painter.drawEllipse(body.adjusted(10, body.height() * 0.82, -10, -body.height() * 0.02))

    def _draw_body(self, painter: QPainter, body: QRectF, alpha_scale: float) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        gradient = QRadialGradient(
            QPointF(body.center().x() - body.width() * 0.12, body.center().y() - body.height() * 0.18),
            body.width() * 0.62,
        )
        gradient.setColorAt(0.0, QColor(ORB_GLOW.red(), ORB_GLOW.green(), ORB_GLOW.blue(), int(242 * alpha_scale)))
        gradient.setColorAt(0.72, QColor(ORB_ORANGE.red(), ORB_ORANGE.green(), ORB_ORANGE.blue(), int(242 * alpha_scale)))
        gradient.setColorAt(1.0, QColor(ORB_FUR.red(), ORB_FUR.green(), ORB_FUR.blue(), int(242 * alpha_scale)))
        painter.setBrush(gradient)
        painter.drawEllipse(body)

    def _draw_fur_halo(self, painter: QPainter, body: QRectF, alpha_scale: float) -> None:
        center = body.center()
        rx = body.width() / 2
        ry = body.height() / 2
        for index in range(112):
            angle = (index / 112.0) * math.tau
            jitter = math.sin(index * 2.17 + self._tick * 0.015)
            radius_x = rx + 0.8 + jitter * 1.1
            radius_y = ry + 0.6 + math.cos(index * 1.73) * 0.9
            dab = QRectF(
                center.x() + math.cos(angle) * radius_x - 2.35,
                center.y() + math.sin(angle) * radius_y - 2.35,
                4.7,
                4.7,
            )
            color = ORB_FUR_DARK if index % 3 == 0 else ORB_FUR
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), int(106 * alpha_scale)))
            painter.drawEllipse(dab)

        for index in range(56):
            angle = (index / 56.0) * math.tau + math.sin(index * 1.37) * 0.035
            length = 1.8 + (math.sin(index * 5.11) + 1.0) * 0.65
            start = QPointF(center.x() + math.cos(angle) * (rx - 0.6), center.y() + math.sin(angle) * (ry - 0.6))
            end = QPointF(center.x() + math.cos(angle) * (rx + length), center.y() + math.sin(angle) * (ry + length))
            color = ORB_FUR if index % 4 else ORB_FUR_DARK
            pen = QPen(QColor(color.red(), color.green(), color.blue(), int(82 * alpha_scale)))
            pen.setWidthF(0.75)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(start, end)

    def _draw_inner_fur(self, painter: QPainter, body: QRectF, alpha_scale: float) -> None:
        center = body.center()
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(54):
            angle = (index / 54.0) * math.tau + math.sin(index) * 0.18
            radius = body.width() * (0.10 + (index % 9) * 0.036)
            start = QPointF(center.x() + math.cos(angle) * radius, center.y() + math.sin(angle) * radius * 0.92)
            end = QPointF(start.x() + math.cos(angle) * 5.8, start.y() + math.sin(angle) * 3.8)
            color = ORB_GLOW if index % 4 == 0 else ORB_FUR
            pen = QPen(QColor(color.red(), color.green(), color.blue(), int(52 * alpha_scale)))
            pen.setWidthF(0.85)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(start, end)

    def _draw_eyes(self, painter: QPainter, body: QRectF, alpha_scale: float) -> None:
        blink = _blink_amount(self._tick)
        gaze = self._gaze_vector(body.width() * 0.030)
        eye_size = body.width() * 0.145
        centers = [
            QPointF(body.center().x() - body.width() * 0.15, body.center().y() - body.height() * 0.040),
            QPointF(body.center().x() + body.width() * 0.15, body.center().y() - body.height() * 0.040),
        ]
        painter.setPen(Qt.PenStyle.NoPen)
        for center in centers:
            height = max(1.4, eye_size * (1.0 - blink * 0.86))
            eye = QRectF(
                center.x() + gaze.x() - eye_size / 2,
                center.y() + gaze.y() - height / 2,
                eye_size,
                height,
            )
            painter.setBrush(QColor(ORB_EYE.red(), ORB_EYE.green(), ORB_EYE.blue(), int(232 * alpha_scale)))
            painter.drawEllipse(eye)
            if blink < 0.72:
                painter.setBrush(QColor(ORB_EYE_SOFT.red(), ORB_EYE_SOFT.green(), ORB_EYE_SOFT.blue(), int(128 * alpha_scale)))
                painter.drawEllipse(eye.adjusted(1.2, eye.height() * 0.52, -1.2, -0.8))
                painter.setBrush(QColor(255, 244, 220, int(218 * alpha_scale)))
                painter.drawEllipse(
                    QPointF(eye.center().x() - eye_size * 0.16, eye.center().y() - eye_size * 0.20),
                    max(1.0, eye_size * 0.18),
                    max(1.0, eye_size * 0.18),
                )

    def _gaze_vector(self, max_offset: float) -> QPointF:
        cursor = QPointF(self.mapFromGlobal(QCursor.pos()))
        center = QPointF(self.width() / 2, self.height() / 2)
        dx = cursor.x() - center.x()
        dy = cursor.y() - center.y()
        distance = math.hypot(dx, dy)
        if 0.01 < distance < 320:
            strength = max_offset * min(1.0, distance / 90.0)
            return QPointF(dx / distance * strength, dy / distance * strength)
        return QPointF(math.sin(self._tick * 0.030) * max_offset * 0.56, math.cos(self._tick * 0.022 + 0.8) * max_offset * 0.38)


def _blink_amount(tick: int) -> float:
    cycle = tick % 150
    if cycle < 136:
        return 0.0
    return math.sin(((cycle - 136) / 14.0) * math.pi)
