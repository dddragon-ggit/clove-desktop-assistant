from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
)

from .main_window_history_layout import MainWindowHistoryLayoutMixin


class MainWindowLayoutMixin(MainWindowHistoryLayoutMixin):
    def _build_header(self, root_layout: QVBoxLayout) -> None:
        header = QHBoxLayout()
        header.setSpacing(10)

        title_group = QVBoxLayout()
        title_group.setSpacing(1)
        title = QLabel("Desktop Assistant")
        title.setObjectName("title")
        subtitle = QLabel("dry-run planning shell")
        subtitle.setObjectName("subtitle")
        title_group.addWidget(title)
        title_group.addWidget(subtitle)

        self.compact_button = QPushButton("Collapse")
        self.compact_button.setObjectName("secondaryButton")
        self.compact_button.clicked.connect(self.toggle_compact)

        close_button = QPushButton("Close")
        close_button.setObjectName("dangerButton")
        close_button.clicked.connect(self.close)

        header.addLayout(title_group, stretch=1)
        header.addWidget(self.compact_button)
        header.addWidget(close_button)
        root_layout.addLayout(header)

    def _build_status(self, root_layout: QVBoxLayout) -> None:
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.status_badge = QLabel("Idle")
        self.status_badge.setObjectName("statusBadge")
        self.risk_badge = QLabel("Risk: -")
        self.risk_badge.setObjectName("riskBadge")
        capability_text = (
            "Capabilities: unavailable"
            if self.capability_catalog_error
            else f"Capabilities: {self.enabled_capability_count}"
        )
        self.capability_badge = QLabel(capability_text)
        self.capability_badge.setObjectName("capabilityBadge")
        self.trace_label = QLabel("Trace: -")
        self.trace_label.setObjectName("traceLabel")
        self.trace_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        status_row.addWidget(self.status_badge)
        status_row.addWidget(self.risk_badge)
        status_row.addWidget(self.capability_badge)
        status_row.addWidget(self.trace_label, stretch=1)
        root_layout.addLayout(status_row)

    def _build_input(self, root_layout: QVBoxLayout) -> None:
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.request_input = QLineEdit()
        self.request_input.setObjectName("requestInput")
        self.request_input.setPlaceholderText("Type a request, e.g. 开始做周报")
        self.request_input.setText("开始做周报")
        self.request_input.returnPressed.connect(self.run_dry_run)

        self.backend_combo = QComboBox()
        self.backend_combo.setObjectName("backendCombo")
        self.backend_combo.addItems(["fake", "real"])

        self.run_button = QPushButton("Dry Run")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self.run_dry_run)
        self.refine_button = QPushButton("Refine")
        self.refine_button.setObjectName("secondaryButton")
        self.refine_button.clicked.connect(self.refine_current_plan)

        input_row.addWidget(self.request_input, stretch=1)
        input_row.addWidget(self.backend_combo)
        input_row.addWidget(self.run_button)
        input_row.addWidget(self.refine_button)
        root_layout.addLayout(input_row)

    def _build_result_area(self, root_layout: QVBoxLayout) -> None:
        if self.app_inventory_error:
            ready_text = f"Ready for a safe dry run. App inventory unavailable: {self.app_inventory_error}"
        else:
            ready_text = f"Ready for a safe dry run. App inventory cached: {self.app_inventory_count} app(s)."
        if self.capability_catalog_error:
            ready_text += f" Capability catalog unavailable: {self.capability_catalog_error}"
        else:
            ready_text += f" Capabilities enabled: {self.enabled_capability_count}."
        self.summary_label = QLabel(ready_text)
        self.summary_label.setObjectName("summaryLabel")
        self.summary_label.setWordWrap(True)
        root_layout.addWidget(self.summary_label)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setObjectName("mainSplitter")
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(6)
        root_layout.addWidget(self.main_splitter, stretch=1)

        self.action_table = QTableWidget(0, 5)
        self.action_table.setObjectName("actionTable")
        self.action_table.setHorizontalHeaderLabels(["Action", "Target", "Risk", "Result", "Reason"])
        self.action_table.verticalHeader().setVisible(False)
        self.action_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.action_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.action_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.action_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.action_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.action_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.action_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.action_table.setMinimumHeight(90)
        self.main_splitter.addWidget(self.action_table)

        review_section = QFrame()
        review_section.setObjectName("splitterSection")
        review_layout = QVBoxLayout(review_section)
        review_layout.setContentsMargins(0, 0, 0, 0)
        review_layout.setSpacing(8)

        self.review_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.review_splitter.setObjectName("reviewSplitter")
        self.review_splitter.setChildrenCollapsible(False)
        self.review_splitter.setHandleWidth(6)
        self.policy_panel = self._make_detail_panel("Policy", "No policy result yet.")
        self.review_panel = self._make_detail_panel("Reviewer", "No review result yet.")
        self.review_splitter.addWidget(self.policy_panel)
        self.review_splitter.addWidget(self.review_panel)
        self.review_splitter.setSizes([1, 1])
        review_layout.addWidget(self.review_splitter, stretch=1)

        self.issues_text = QTextEdit()
        self.issues_text.setObjectName("issuesText")
        self.issues_text.setReadOnly(True)
        self.issues_text.setMinimumHeight(64)
        self.issues_text.setPlainText("No issues.")
        review_layout.addWidget(self.issues_text, stretch=1)

        self.confirmation_panel = QFrame()
        self.confirmation_panel.setObjectName("confirmationPanel")
        confirmation_layout = QVBoxLayout(self.confirmation_panel)
        confirmation_layout.setContentsMargins(12, 10, 12, 12)
        confirmation_layout.setSpacing(8)
        self.confirmation_label = QLabel("No plan awaiting decision.")
        self.confirmation_label.setObjectName("confirmationLabel")
        self.confirmation_label.setWordWrap(True)
        confirmation_layout.addWidget(self.confirmation_label)

        decision_row = QHBoxLayout()
        decision_row.setSpacing(8)
        self.reject_button = QPushButton("Reject")
        self.reject_button.setObjectName("dangerButton")
        self.reject_button.clicked.connect(lambda: self.record_decision("rejected"))
        self.run_once_button = QPushButton("Run Once")
        self.run_once_button.setObjectName("primaryButton")
        self.run_once_button.clicked.connect(self.run_once_current_trace)
        self.whitelist_button = QPushButton("Whitelist")
        self.whitelist_button.setObjectName("secondaryButton")
        self.whitelist_button.clicked.connect(self.whitelist_current_actions)
        self.save_recipe_button = QPushButton("Save Recipe")
        self.save_recipe_button.setObjectName("secondaryButton")
        self.save_recipe_button.clicked.connect(self.save_current_recipe)
        decision_row.addWidget(self.reject_button)
        decision_row.addWidget(self.run_once_button)
        decision_row.addWidget(self.whitelist_button)
        decision_row.addWidget(self.save_recipe_button)
        confirmation_layout.addLayout(decision_row)
        review_layout.addWidget(self.confirmation_panel)
        self._set_decision_buttons(False)

        self.main_splitter.addWidget(review_section)

        self._build_history_section()
        self.main_splitter.setSizes([240, 260, 280])
        self._refresh_capability_list()
        self._refresh_trust_list()
        self._refresh_recipe_list()
        self._refresh_project_list()
        self._refresh_window_list()
