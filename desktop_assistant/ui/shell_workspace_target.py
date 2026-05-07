from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFileDialog, QPushButton, QWidget

from . import shell_text as text

APP_ACTIONS = {"open_app", "focus_app"}
FILE_ACTIONS = {"open_file", "open_folder"}


def target_text(combo: QComboBox) -> str:
    return combo.currentText().strip()


def set_target_text(combo: QComboBox, value: str) -> None:
    combo.setEditText(value.strip())


def configure_target_input(
    combo: QComboBox,
    action_type: str,
    app_names: list[str],
    browse_button: QPushButton,
) -> None:
    current = target_text(combo)
    combo.blockSignals(True)
    combo.clear()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    combo.setMaxVisibleItems(12)
    if action_type in APP_ACTIONS:
        combo.addItems(app_names)
    combo.setCurrentIndex(-1)
    set_target_text(combo, current)
    _set_placeholder(combo, _placeholder(action_type))
    _configure_completer(combo)
    combo.blockSignals(False)
    _configure_browse_button(browse_button, action_type)


def browse_target(parent: QWidget, action_type: str) -> str:
    if action_type == "open_file":
        path, _selected_filter = QFileDialog.getOpenFileName(parent, text.TODO_SELECT_FILE_TITLE)
        return path.strip()
    if action_type == "open_folder":
        return QFileDialog.getExistingDirectory(parent, text.TODO_SELECT_FOLDER_TITLE).strip()
    return ""


def _configure_completer(combo: QComboBox) -> None:
    completer = combo.completer()
    if completer is None:
        return
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCompletionMode(completer.CompletionMode.PopupCompletion)


def _set_placeholder(combo: QComboBox, value: str) -> None:
    line_edit = combo.lineEdit()
    if line_edit is not None:
        line_edit.setPlaceholderText(value)


def _configure_browse_button(button: QPushButton, action_type: str) -> None:
    button.setVisible(action_type in FILE_ACTIONS)
    if action_type == "open_file":
        button.setText(text.TODO_SELECT_FILE)
    elif action_type == "open_folder":
        button.setText(text.TODO_SELECT_FOLDER)
    else:
        button.setText(text.TODO_SELECT_TARGET)


def _placeholder(action_type: str) -> str:
    if action_type in APP_ACTIONS:
        return text.TODO_ACTION_APP_PLACEHOLDER
    if action_type == "open_file":
        return text.TODO_ACTION_FILE_PLACEHOLDER
    if action_type == "open_folder":
        return text.TODO_ACTION_FOLDER_PLACEHOLDER
    return text.TODO_ACTION_TARGET_PLACEHOLDER
