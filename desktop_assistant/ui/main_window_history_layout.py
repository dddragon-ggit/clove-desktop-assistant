from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QSplitter, QTextEdit, QVBoxLayout

from .main_window_operational_layout import MainWindowOperationalLayoutMixin
from .main_window_resource_layout import MainWindowResourceLayoutMixin


class MainWindowHistoryLayoutMixin(
    MainWindowOperationalLayoutMixin,
    MainWindowResourceLayoutMixin,
):
    def _build_history_section(self) -> None:
        history_section = QFrame()
        history_section.setObjectName("splitterSection")
        history_layout = QVBoxLayout(history_section)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.setSpacing(0)
        self.history_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.history_splitter.setObjectName("historySplitter")
        self.history_splitter.setChildrenCollapsible(False)
        self.history_splitter.setHandleWidth(6)
        history_layout.addWidget(self.history_splitter)

        history_lists = QFrame()
        history_lists.setObjectName("splitterSection")
        history_lists_layout = QVBoxLayout(history_lists)
        history_lists_layout.setContentsMargins(0, 0, 0, 0)
        history_lists_layout.setSpacing(8)

        self.list_splitter = QSplitter(Qt.Orientation.Vertical)
        self.list_splitter.setObjectName("listSplitter")
        self.list_splitter.setChildrenCollapsible(False)
        self.list_splitter.setHandleWidth(6)
        history_lists_layout.addWidget(self.list_splitter)

        self._add_recent_block()
        self._add_debug_block()
        self._add_recovery_block()
        self._add_capability_block()
        self._add_window_block()
        self._add_whitelist_block()
        self._add_recipe_block()
        self._add_project_block()
        self.list_splitter.setSizes([1, 1, 1, 1, 1, 1, 1, 1])

        self.debug_snapshot_text = QTextEdit()
        self.debug_snapshot_text.setObjectName("debugSnapshotText")
        self.debug_snapshot_text.setReadOnly(True)
        self.debug_snapshot_text.setMinimumHeight(120)
        self.debug_snapshot_text.setPlainText("Select a debug run to inspect its snapshot.")
        self.history_splitter.addWidget(history_lists)
        self.history_splitter.addWidget(self.debug_snapshot_text)
        self.history_splitter.setSizes([260, 420])
        self.main_splitter.addWidget(history_section)
