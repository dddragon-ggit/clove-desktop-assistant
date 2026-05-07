from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


TRAY_SHOW_PANEL_TEXT = "显示面板"
TRAY_SHOW_ORB_TEXT = "显示小球"
TRAY_HEALTH_TEXT = "健康面板"
TRAY_REFRESH_APPS_TEXT = "刷新应用清单"
TRAY_QUIT_TEXT = "退出"


def build_tray_icon(color: str) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    status_color = _parse_color(color)
    ring_color = QColor(255, 255, 255, 228)
    shadow_color = QColor(17, 24, 39, 90)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(shadow_color)
    painter.drawEllipse(8, 8, 48, 48)

    painter.setBrush(status_color)
    painter.drawEllipse(10, 10, 44, 44)

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(ring_color, 3))
    painter.drawEllipse(11, 11, 42, 42)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 238))
    for index, height in enumerate((18, 28, 22)):
        x = 20 + (index * 9)
        y = 32 - (height // 2)
        painter.drawRoundedRect(x, y, 6, height, 3, 3)

    painter.end()
    return QIcon(pixmap)


def tray_tooltip(app_title: str, *, open_count: int, next_task_title: str | None) -> str:
    lines = [app_title, f"待办数量：{open_count}"]
    if next_task_title:
        lines.append(f"下一项：{next_task_title}")
    else:
        lines.append("下一项：无")
    return "\n".join(lines)


def _parse_color(value: str) -> QColor:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        return QColor("#2E7D5B")
    try:
        return QColor(f"#{clean}")
    except Exception:
        return QColor("#2E7D5B")
