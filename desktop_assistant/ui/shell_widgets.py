from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit

from .shell_text import PREDICTION_PLACEHOLDER


class PredictionInput(QLineEdit):
    predictionAccepted = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._prediction_text = ""

    def set_prediction(self, text: str) -> None:
        self._prediction_text = text.strip()
        self.setPlaceholderText(self._prediction_text or PREDICTION_PLACEHOLDER)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Tab and self._prediction_text:
            self.setText(self._prediction_text)
            self.predictionAccepted.emit(self._prediction_text)
            event.accept()
            return
        super().keyPressEvent(event)
