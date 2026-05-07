from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from . import shell_text as text
from .shell_widgets import PredictionInput


def shell_button(label: str, handler, object_name: str) -> QPushButton:  # type: ignore[no-untyped-def]
    button = QPushButton(label)
    button.setObjectName(object_name)
    button.clicked.connect(handler)
    return button


def prediction_input(owner) -> PredictionInput:  # type: ignore[no-untyped-def]
    widget = PredictionInput()
    widget.setObjectName("predictionInput")
    widget.returnPressed.connect(lambda w=widget: owner._submit_text(w.text(), False))
    widget.predictionAccepted.connect(lambda value: owner._submit_text(value, True))
    return widget


def page_header(title: str, back_handler) -> QHBoxLayout:  # type: ignore[no-untyped-def]
    row = QHBoxLayout()
    label = QLabel(title)
    label.setObjectName("pageTitle")
    row.addWidget(shell_button(text.BACK, back_handler, "iconButton"))
    accent = QFrame()
    accent.setObjectName("pageAccent")
    accent.setFixedSize(5, 18)
    row.addWidget(accent)
    row.addWidget(label, stretch=1)
    return row


def centered_title(label: str) -> QLabel:
    widget = QLabel(label)
    widget.setObjectName("pageTitle")
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget


def surface_card() -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("shellSurface")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)
    return card, layout


def section_label(label: str) -> QLabel:
    widget = QLabel(label)
    widget.setObjectName("sectionLabel")
    return widget
