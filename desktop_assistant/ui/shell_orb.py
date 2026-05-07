from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


PET_WINDOW_WIDTH = 124
PET_WINDOW_HEIGHT = 146
ATLAS_COLUMNS = 8
ATLAS_ROWS = 9
CELL_WIDTH = 192
CELL_HEIGHT = 208
DEFAULT_STATUS_COLOR = QColor("#2E7D5B")
DEFAULT_PET_ID = "mudie"
DEFAULT_DESKTOP_PET_DIR = Path.cwd() / "runtime" / "pets" / DEFAULT_PET_ID
PROJECT_RUNTIME_PET_DIR = Path(__file__).resolve().parents[2] / "runtime" / "pets" / DEFAULT_PET_ID

STATE_SPECS: dict[str, tuple[int, list[int]]] = {
    "idle": (0, [280, 110, 110, 140, 140, 320]),
    "running-right": (1, [120, 120, 120, 120, 120, 120, 120, 220]),
    "running-left": (2, [120, 120, 120, 120, 120, 120, 120, 220]),
    "waving": (3, [140, 140, 140, 280]),
    "jumping": (4, [140, 140, 140, 140, 280]),
    "failed": (5, [140, 140, 140, 140, 140, 140, 140, 240]),
    "waiting": (6, [150, 150, 150, 150, 150, 260]),
    "running": (7, [120, 120, 120, 120, 120, 220]),
    "review": (8, [150, 150, 150, 150, 150, 280]),
}

STATUS_STATES = {
    "#c2413b": "review",
    "#d97706": "running-right",
    "#c99a1a": "waiting",
    "#2e7d5b": "idle",
}


@dataclass(slots=True)
class PetPackage:
    pet_id: str
    display_name: str
    description: str
    spritesheet: QImage


class LivingOrb(QWidget):
    """Transparent floating desktop pet that replaces the old audio-wave orb."""

    def __init__(self) -> None:
        super().__init__()
        self._hidden = False
        self._status_color = QColor(DEFAULT_STATUS_COLOR)
        self._state = "idle"
        self._base_state = "idle"
        self._held_state: str | None = None
        self._drag_state: str | None = None
        self._frame_index = 0
        self._oneshot_state: str | None = None
        self._ambient_index = 0
        self._package = _discover_pet_package()
        self.setMinimumSize(PET_WINDOW_WIDTH, PET_WINDOW_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(_current_frame_duration(self._state, self._frame_index))
        self._ambient_timer = QTimer(self)
        self._ambient_timer.timeout.connect(self._play_ambient)
        self._ambient_timer.start(9000)
        QTimer.singleShot(3500, self._play_ambient)

    def set_color(self, value: str) -> None:
        color = QColor(value)
        self._status_color = color if color.isValid() else QColor(DEFAULT_STATUS_COLOR)
        self._base_state = _state_for_color(self._status_color)
        if self._drag_state is None and self._oneshot_state is None and self._held_state is None:
            self._set_state(self._base_state)
        self.update()

    def set_hidden_mode(self, hidden: bool) -> None:
        self._hidden = hidden
        self.update()

    def play_once(self, state: str) -> None:
        if state not in STATE_SPECS:
            return
        self._oneshot_state = state
        if self._drag_state is None:
            self._set_state(state, force=True)

    def hold_state(self, state: str) -> None:
        if state not in STATE_SPECS:
            return
        self._oneshot_state = None
        self._held_state = state
        if self._drag_state is None:
            self._set_state(state, force=True)

    def release_hold(self) -> None:
        self._held_state = None
        if self._drag_state is None and self._oneshot_state is None:
            self._set_state(self._base_state)

    def hold_drag_state(self, state: str) -> None:
        if state not in STATE_SPECS:
            return
        force = self._drag_state is None or self._state != state
        self._drag_state = state
        self._set_state(state, force=force)

    def release_drag_state(self) -> None:
        if self._drag_state is None:
            return
        self._drag_state = None
        self._set_state(self._oneshot_state or self._held_state or self._base_state, force=True)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        alpha_scale = 0.34 if self._hidden else 1.0
        if self._package is not None:
            self._draw_packaged_pet(painter, alpha_scale)
        else:
            self._draw_fallback_pet(painter, alpha_scale)
        painter.end()

    def _advance(self) -> None:
        frame_count = len(STATE_SPECS[self._state][1])
        self._frame_index = (self._frame_index + 1) % frame_count
        if self._oneshot_state == self._state and self._frame_index == 0:
            self._oneshot_state = None
            self._set_state(self._held_state or self._base_state)
            frame_count = len(STATE_SPECS[self._state][1])
        self._timer.start(_current_frame_duration(self._state, self._frame_index))
        self.update()

    def _set_state(self, state: str, *, force: bool = False) -> None:
        if state not in STATE_SPECS or (state == self._state and not force):
            return
        self._state = state
        self._frame_index = 0
        self._timer.start(_current_frame_duration(self._state, self._frame_index))

    def _play_ambient(self) -> None:
        if not self.isVisible() or self._hidden or self._oneshot_state is not None or self._held_state is not None:
            return
        self.play_once(self._next_ambient_state())
        self._ambient_timer.start(8000 + (self._ambient_index % 3) * 2000)

    def _next_ambient_state(self) -> str:
        self._ambient_index += 1
        if self._base_state == "review":
            return "jumping"
        if self._base_state in {"idle", "waiting"}:
            return "waving" if self._ambient_index % 2 else "jumping"
        return "jumping" if self._ambient_index % 2 else "waving"

    def _draw_packaged_pet(self, painter: QPainter, alpha_scale: float) -> None:
        if self._package is None:
            return
        row, durations = STATE_SPECS[self._state]
        column = min(self._frame_index, len(durations) - 1)
        source = QRectF(column * CELL_WIDTH, row * CELL_HEIGHT, CELL_WIDTH, CELL_HEIGHT)
        target = QRectF(4, 2, self.width() - 8, self.height() - 4)
        painter.setOpacity(alpha_scale)
        painter.drawImage(target, self._package.spritesheet, source)
        painter.setOpacity(1.0)
        self._draw_status_butterfly(painter, alpha_scale)

    def _draw_fallback_pet(self, painter: QPainter, alpha_scale: float) -> None:
        painter.setOpacity(alpha_scale)

        body = QRectF(22, 20, self.width() - 44, self.height() - 30)
        head = QRectF(body.left() + 6, body.top(), body.width() - 12, body.height() * 0.54)
        torso = QRectF(body.left() + 14, head.bottom() - 4, body.width() - 28, body.height() * 0.34)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(41, 46, 63, 228))
        painter.drawRoundedRect(torso, 16, 16)

        painter.setBrush(QColor(247, 224, 214, 242))
        painter.drawEllipse(head)

        hair = QPainterPath()
        hair.moveTo(head.left() + 4, head.center().y() - 10)
        hair.cubicTo(head.left() - 4, head.top() + 6, head.left() + 12, head.top() - 4, head.center().x(), head.top() + 3)
        hair.cubicTo(head.right() - 16, head.top() - 4, head.right() + 2, head.top() + 6, head.right() - 2, head.center().y() + 10)
        hair.lineTo(head.right() - 12, head.bottom() - 10)
        hair.cubicTo(head.center().x() + 8, head.bottom() + 8, head.center().x() - 8, head.bottom() + 4, head.left() + 10, head.bottom() - 4)
        hair.closeSubpath()
        hair_gradient = QLinearGradient(head.topLeft(), head.topRight())
        hair_gradient.setColorAt(0.0, QColor(85, 156, 239, 245))
        hair_gradient.setColorAt(0.48, QColor(121, 181, 255, 238))
        hair_gradient.setColorAt(0.52, QColor(250, 166, 210, 238))
        hair_gradient.setColorAt(1.0, QColor(240, 112, 191, 245))
        painter.setBrush(hair_gradient)
        painter.drawPath(hair)

        painter.setBrush(QColor(72, 80, 96, 245))
        painter.drawEllipse(QRectF(head.left() + 17, head.center().y() + 2, 7, 10))
        painter.drawEllipse(QRectF(head.right() - 24, head.center().y() + 2, 7, 10))

        pen = QPen(QColor(88, 64, 88, 220))
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRectF(head.center().x() - 10, head.bottom() - 18, 20, 10), 0, -180 * 16)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(32, 36, 52, 250))
        painter.drawRoundedRect(QRectF(torso.left() - 6, torso.top() + 12, torso.width() + 12, torso.height() - 4), 18, 18)
        painter.drawRoundedRect(QRectF(torso.left() - 10, torso.center().y() - 3, 14, 10), 6, 6)
        painter.drawRoundedRect(QRectF(torso.right() - 4, torso.center().y() - 5, 14, 10), 6, 6)
        painter.drawRoundedRect(QRectF(torso.left() + 6, torso.bottom() - 2, 10, 16), 5, 5)
        painter.drawRoundedRect(QRectF(torso.right() - 16, torso.bottom() - 2, 10, 16), 5, 5)

        badge = QRectF(head.right() - 18, head.top() + 8, 16, 12)
        self._draw_butterfly_shape(painter, badge, QColor(180, 211, 255, 240), QColor(249, 177, 220, 240))
        self._draw_status_butterfly(painter, alpha_scale)
        painter.setOpacity(1.0)

    def _draw_status_butterfly(self, painter: QPainter, alpha_scale: float) -> None:
        badge = QRectF(self.width() - 28, 4, 20, 16)
        left_wing = _mix(self._status_color, QColor("#FFFFFF"), 0.22)
        right_wing = _mix(self._status_color, QColor("#FFFFFF"), 0.45)
        self._draw_butterfly_shape(
            painter,
            badge,
            _with_alpha(left_wing, int(226 * alpha_scale)),
            _with_alpha(right_wing, int(216 * alpha_scale)),
        )

    def _draw_butterfly_shape(self, painter: QPainter, rect: QRectF, left_color: QColor, right_color: QColor) -> None:
        center_x = rect.center().x()
        center_y = rect.center().y()

        painter.setPen(QPen(QColor(31, 36, 46, 210), 1.1))
        painter.setBrush(left_color)
        painter.drawEllipse(QRectF(rect.left(), rect.top(), rect.width() * 0.45, rect.height() * 0.58))
        painter.drawEllipse(QRectF(rect.left() + 1, center_y - 2, rect.width() * 0.38, rect.height() * 0.42))

        painter.setBrush(right_color)
        painter.drawEllipse(QRectF(center_x + 1, rect.top(), rect.width() * 0.45, rect.height() * 0.58))
        painter.drawEllipse(QRectF(center_x + 3, center_y - 2, rect.width() * 0.38, rect.height() * 0.42))

        painter.setBrush(QColor(33, 38, 54, 230))
        painter.drawRoundedRect(QRectF(center_x - 1.5, rect.top() + 1, 3, rect.height() - 3), 1.5, 1.5)


def _current_frame_duration(state: str, frame_index: int) -> int:
    durations = STATE_SPECS.get(state, STATE_SPECS["idle"])[1]
    return durations[min(frame_index, len(durations) - 1)]


def _state_for_color(color: QColor) -> str:
    key = color.name().lower()
    return STATUS_STATES.get(key, "idle")


def _discover_pet_package() -> PetPackage | None:
    candidates = []
    override = _pet_dir_override()
    if override:
        candidates.append(Path(override))
    candidates.extend(
        [
            DEFAULT_DESKTOP_PET_DIR,
            PROJECT_RUNTIME_PET_DIR,
            Path.home() / ".codex" / "pets" / DEFAULT_PET_ID,
        ]
    )
    for directory in candidates:
        package = _load_pet_package(directory)
        if package is not None:
            return package
    return None


def _pet_dir_override() -> str:
    return os.environ.get("DESKTOP_ASSISTANT_PET_DIR", "")


def _load_pet_package(directory: Path) -> PetPackage | None:
    manifest_path = directory / "pet.json"
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    spritesheet = _load_spritesheet(directory, str(payload.get("spritesheetPath") or "spritesheet.webp"))
    if spritesheet is None:
        return None
    if spritesheet.width() != ATLAS_COLUMNS * CELL_WIDTH or spritesheet.height() != ATLAS_ROWS * CELL_HEIGHT:
        return None
    return PetPackage(
        pet_id=str(payload.get("id") or directory.name),
        display_name=str(payload.get("displayName") or directory.name),
        description=str(payload.get("description") or ""),
        spritesheet=spritesheet,
    )


def _load_spritesheet(directory: Path, manifest_path: str) -> QImage | None:
    for sheet_path in _spritesheet_candidates(directory, manifest_path):
        if not sheet_path.exists():
            continue
        spritesheet = QImage(str(sheet_path))
        if not spritesheet.isNull():
            return spritesheet
    return None


def _spritesheet_candidates(directory: Path, manifest_path: str) -> list[Path]:
    primary = directory / manifest_path
    candidates = [
        primary,
        primary.with_suffix(".png"),
        directory / "spritesheet.png",
        directory / "spritesheet.webp",
    ]
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(candidate)
    return unique


def _mix(color: QColor, other: QColor, amount: float) -> QColor:
    ratio = max(0.0, min(1.0, amount))
    return QColor(
        round(color.red() * (1 - ratio) + other.red() * ratio),
        round(color.green() * (1 - ratio) + other.green() * ratio),
        round(color.blue() * (1 - ratio) + other.blue() * ratio),
    )


def _with_alpha(color: QColor, alpha: int) -> QColor:
    return QColor(color.red(), color.green(), color.blue(), max(0, min(255, alpha)))
