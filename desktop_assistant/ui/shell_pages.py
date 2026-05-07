from __future__ import annotations

import os

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizeGrip, QStackedWidget, QTextEdit, QVBoxLayout, QWidget

from . import shell_text as text
from .shell_page_helpers import centered_title, page_header, prediction_input, shell_button
from .shell_reminder_pages import build_reminder_settings_page
from .shell_todo_pages import build_todo_detail_page, build_todo_page
from .shell_workspace_pages import build_workspace_confirm_page, build_workspace_page


class ShellPagesMixin:
    def _build_panel(self) -> None:
        layout = QVBoxLayout(self.panel_body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(self._top_bar())
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, stretch=1)

        self.glance_page = self._build_glance_page()
        self.menu_page = self._build_menu_page()
        self.todo_page = build_todo_page(self)
        self.todo_detail_page = build_todo_detail_page(self)
        self.reminder_settings_page = build_reminder_settings_page(self)
        self.workspace_confirm_page = build_workspace_confirm_page(self)
        self.workspace_page = build_workspace_page(self)
        self.chat_page = self._build_chat_page()
        for page in [
            self.glance_page,
            self.menu_page,
            self.todo_page,
            self.todo_detail_page,
            self.reminder_settings_page,
            self.workspace_confirm_page,
            self.workspace_page,
            self.chat_page,
        ]:
            self.stack.addWidget(page)

        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        grip_row.addWidget(QSizeGrip(self.root))
        layout.addLayout(grip_row)

    def _top_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.shell_title = QLabel(text.APP_TITLE)
        self.shell_title.setObjectName("smallNote")
        self.backend_combo = QComboBox()
        self.backend_combo.setObjectName("backendCombo")
        self.backend_combo.addItems(["real", "fake"])
        if os.getenv("DESKTOP_ASSISTANT_UI_BACKEND") == "fake":
            self.backend_combo.setCurrentText("fake")
        row.addWidget(self.shell_title, stretch=1)
        row.addWidget(self.backend_combo)
        row.addWidget(shell_button(text.BACK_HOME, self._show_glance, "iconButton"))
        row.addWidget(shell_button(text.MINIMIZE, self._show_orb, "iconButton"))
        row.addWidget(shell_button(text.CLOSE, self._show_orb, "iconButton"))
        return row

    def _build_glance_page(self) -> QWidget:
        page = QWidget()
        page.mousePressEvent = lambda event: self._show_menu()  # type: ignore[method-assign]
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 8, 2, 0)
        layout.setSpacing(8)
        layout.addStretch(1)
        self.greeting_label = QLabel("")
        self.greeting_label.setObjectName("heroGreeting")
        self.count_label = QLabel("")
        self.count_label.setObjectName("heroCount")
        self.next_label = QLabel("")
        self.next_label.setObjectName("heroNext")
        self.recovery_label = QLabel("")
        self.recovery_label.setObjectName("smallNote")
        self.recovery_label.setWordWrap(True)
        self.recovery_label.setVisible(False)
        layout.addWidget(self.greeting_label)
        layout.addWidget(self.count_label)
        layout.addWidget(self.next_label)
        layout.addWidget(self.recovery_label)
        layout.addStretch(1)
        self.glance_input = prediction_input(self)
        layout.addWidget(self.glance_input)
        return page

    def _build_menu_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 14, 24, 4)
        layout.setSpacing(14)
        layout.addWidget(centered_title(text.MENU_TITLE))
        layout.addWidget(shell_button(text.MENU_TODO, self._show_todo_page, "navButton"))
        layout.addWidget(shell_button(text.MENU_WORKSPACE, self._show_workspace_page, "navButton"))
        layout.addWidget(shell_button(text.MENU_CONTINUE, self._continue_from_prediction, "navButton"))
        layout.addStretch(1)
        self.menu_input = prediction_input(self)
        layout.addWidget(self.menu_input)
        return page

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(page_header(text.CHAT_TITLE, self._show_menu))
        self.chat_text = QTextEdit()
        self.chat_text.setObjectName("chatText")
        self.chat_text.setReadOnly(True)
        layout.addWidget(self.chat_text, stretch=1)
        row = QHBoxLayout()
        self.run_once_button = shell_button(text.CHAT_RUN_ONCE, self._execute_latest_trace, "primaryShellButton")
        self.run_once_button.setEnabled(False)
        row.addWidget(self.run_once_button)
        row.addStretch(1)
        layout.addLayout(row)
        return page
