from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import shell_text as text
from .shell_page_helpers import page_header, section_label, shell_button, surface_card


def build_todo_page(owner) -> QWidget:  # type: ignore[no-untyped-def]
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)
    layout.addLayout(page_header(text.TODO_TITLE, owner._show_menu))
    list_card, list_layout = surface_card()
    hint = QLabel(text.TODO_LIST_HINT)
    hint.setObjectName("smallNote")
    list_layout.addWidget(hint)
    owner.todo_feedback_label = QLabel("")
    owner.todo_feedback_label.setObjectName("smallNote")
    owner.todo_feedback_label.setWordWrap(True)
    owner.todo_feedback_label.setVisible(False)
    list_layout.addWidget(owner.todo_feedback_label)
    owner.todo_list = QListWidget()
    owner.todo_list.setObjectName("todoList")
    owner.todo_list.itemClicked.connect(lambda *_: owner._todo_selection_changed())
    owner.todo_list.itemActivated.connect(lambda *_: owner._todo_selection_changed())
    list_layout.addWidget(owner.todo_list, stretch=1)
    layout.addWidget(list_card, stretch=1)

    quick_card, quick_layout = surface_card()
    quick_row = QHBoxLayout()
    owner.todo_quick_input = QLineEdit()
    owner.todo_quick_input.setObjectName("todoQuickInput")
    owner.todo_quick_input.setPlaceholderText(text.TODO_QUICK_ADD_PLACEHOLDER)
    owner.todo_quick_input.returnPressed.connect(owner._quick_add_todo)
    quick_row.addWidget(owner.todo_quick_input, stretch=1)
    owner.todo_quick_type_combo = QComboBox()
    owner.todo_quick_type_combo.setObjectName("todoQuickTypeCombo")
    for label, value in text.TODO_TASK_TYPE_ITEMS:
        owner.todo_quick_type_combo.addItem(label, value)
    quick_row.addWidget(owner.todo_quick_type_combo)
    quick_row.addWidget(shell_button(text.TODO_ADD, owner._quick_add_todo, "primaryShellButton"))
    quick_row.addWidget(shell_button(text.TODO_REMINDER_SETTINGS, owner._show_reminder_settings_page, "secondaryShellButton"))
    quick_layout.addLayout(quick_row)
    layout.addWidget(quick_card)
    return page


def build_todo_detail_page(owner) -> QWidget:  # type: ignore[no-untyped-def]
    page = QWidget()
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(0, 0, 0, 0)
    page_layout.setSpacing(7)
    page_layout.addLayout(page_header(text.TODO_TITLE, owner._show_todo_page))
    scroll = QScrollArea()
    scroll.setObjectName("todoDetailScroll")
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    content.setObjectName("todoDetailContent")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)

    detail_card, detail_layout = surface_card()
    detail_layout.addWidget(section_label(text.TODO_TITLE))
    owner.todo_detail = QTextEdit()
    owner.todo_detail.setObjectName("todoDetail")
    owner.todo_detail.setReadOnly(True)
    owner.todo_detail.setMinimumHeight(112)
    owner.todo_detail.setMaximumHeight(150)
    owner.todo_detail.setPlainText(text.TODO_DETAIL_EMPTY)
    detail_layout.addWidget(owner.todo_detail)
    layout.addWidget(detail_card)

    workspace_card, workspace_layout = surface_card()
    workspace_layout.addWidget(section_label(text.WORKSPACE_ACTION_SECTION))
    owner.workspace_action_list = QListWidget()
    owner.workspace_action_list.setObjectName("workspaceActionList")
    owner.workspace_action_list.setMinimumHeight(92)
    owner.workspace_action_list.setMaximumHeight(130)
    owner.workspace_action_list.itemChanged.connect(lambda *_: owner._workspace_action_selection_changed())
    workspace_layout.addWidget(owner.workspace_action_list)
    _add_workspace_action_editor(owner, workspace_layout)
    layout.addWidget(workspace_card)

    edit_card, edit_layout = surface_card()
    edit_layout.addWidget(section_label(text.TODO_SAVE_CHANGES))
    _add_todo_editor(owner, edit_layout)
    layout.addWidget(edit_card)

    action_card, action_layout = surface_card()
    _add_todo_action_row(owner, action_layout)
    layout.addWidget(action_card)

    scroll.setWidget(content)
    page_layout.addWidget(scroll, stretch=1)
    owner._set_todo_execution_buttons(False, False)
    owner._set_todo_edit_buttons(False)
    return page


def _add_workspace_action_editor(owner, layout: QVBoxLayout) -> None:  # type: ignore[no-untyped-def]
    target_row = QHBoxLayout()
    owner.workspace_action_type_combo = QComboBox()
    owner.workspace_action_type_combo.setObjectName("workspaceActionTypeCombo")
    for label, value in text.TODO_ACTION_TYPE_ITEMS:
        owner.workspace_action_type_combo.addItem(label, value)
    owner.workspace_action_target_input = QComboBox()
    owner.workspace_action_target_input.setObjectName("workspaceActionTargetInput")
    owner.workspace_action_target_input.setEditable(True)
    owner.workspace_action_target_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    owner.workspace_action_type_combo.currentIndexChanged.connect(lambda *_: owner._workspace_action_type_changed())
    target_row.addWidget(owner.workspace_action_type_combo)
    target_row.addWidget(owner.workspace_action_target_input, stretch=1)
    owner.workspace_action_browse_button = shell_button(
        text.TODO_SELECT_TARGET,
        owner._browse_workspace_action_target,
        "secondaryShellButton",
    )
    owner.workspace_action_browse_button.setVisible(False)
    target_row.addWidget(owner.workspace_action_browse_button)
    layout.addLayout(target_row)

    action_edit_row = QHBoxLayout()
    action_edit_row.addWidget(shell_button(text.TODO_ADD_WORKSPACE_ACTION, owner._add_workspace_action, "secondaryShellButton"))
    owner.todo_save_workspace_button = shell_button(
        text.TODO_SAVE_WORKSPACE_BINDING,
        owner._save_selected_workspace_binding,
        "secondaryShellButton",
    )
    action_edit_row.addWidget(owner.todo_save_workspace_button)
    layout.addLayout(action_edit_row)

    confirm_row = QHBoxLayout()
    owner.todo_reject_button = shell_button(text.TODO_REJECT_WORKSPACE, owner._reject_selected_workspace, "secondaryShellButton")
    owner.todo_run_once_button = shell_button(text.TODO_RUN_WORKSPACE_ONCE, owner._run_selected_workspace_once, "primaryShellButton")
    owner.todo_trust_button = shell_button(text.TODO_TRUST_WORKSPACE, owner._trust_selected_workspace, "secondaryShellButton")
    confirm_row.addWidget(owner.todo_reject_button)
    confirm_row.addWidget(owner.todo_run_once_button)
    confirm_row.addWidget(owner.todo_trust_button)
    layout.addLayout(confirm_row)


def _add_todo_editor(owner, layout: QVBoxLayout) -> None:  # type: ignore[no-untyped-def]
    add_row = QHBoxLayout()
    owner.todo_input = QLineEdit()
    owner.todo_input.setObjectName("todoInput")
    owner.todo_input.setPlaceholderText(text.TODO_ADD_PLACEHOLDER)
    add_row.addWidget(owner.todo_input, stretch=1)
    owner.todo_save_button = shell_button(text.TODO_SAVE_CHANGES, owner._save_selected_todo_changes, "secondaryShellButton")
    add_row.addWidget(owner.todo_save_button)
    layout.addLayout(add_row)

    description_row = QHBoxLayout()
    owner.todo_description_input = QLineEdit()
    owner.todo_description_input.setObjectName("todoDescriptionInput")
    owner.todo_description_input.setPlaceholderText(text.TODO_DESCRIPTION_PLACEHOLDER)
    description_row.addWidget(owner.todo_description_input, stretch=1)
    owner.needs_computer_check = QCheckBox(text.TODO_NEEDS_COMPUTER)
    owner.needs_computer_check.setObjectName("smallNote")
    description_row.addWidget(owner.needs_computer_check)
    owner.todo_cancel_item_button = shell_button(text.TODO_CANCEL_ITEM, owner._cancel_selected_todo, "secondaryShellButton")
    description_row.addWidget(owner.todo_cancel_item_button)
    layout.addLayout(description_row)

    meta_row = QHBoxLayout()
    owner.todo_time_input = QLineEdit()
    owner.todo_time_input.setObjectName("todoTimeInput")
    owner.todo_time_input.setPlaceholderText(text.TODO_TIME_PLACEHOLDER)
    owner.todo_priority_combo = QComboBox()
    owner.todo_priority_combo.setObjectName("todoPriorityCombo")
    for label, value in text.TODO_PRIORITY_ITEMS:
        owner.todo_priority_combo.addItem(label, value)
    owner.todo_type_combo = QComboBox()
    owner.todo_type_combo.setObjectName("todoTypeCombo")
    for label, value in text.TODO_TASK_TYPE_ITEMS:
        owner.todo_type_combo.addItem(label, value)
    owner.important_check = QCheckBox(text.TODO_IMPORTANT)
    owner.important_check.setObjectName("smallNote")
    meta_row.addWidget(owner.todo_time_input, stretch=1)
    meta_row.addWidget(owner.todo_priority_combo)
    meta_row.addWidget(owner.todo_type_combo)
    meta_row.addWidget(owner.important_check)
    layout.addLayout(meta_row)


def _add_todo_action_row(owner, layout: QVBoxLayout) -> None:  # type: ignore[no-untyped-def]
    action_row = QHBoxLayout()
    action_row.addWidget(shell_button(text.TODO_COMPLETE, owner._complete_selected_todo, "secondaryShellButton"))
    action_row.addWidget(shell_button(text.TODO_POSTPONE, owner._postpone_selected_todo, "secondaryShellButton"))
    action_row.addWidget(shell_button(text.TODO_SKIP_TODAY, owner._skip_selected_todo_today, "secondaryShellButton"))
    action_row.addWidget(shell_button(text.TODO_DELETE, owner._delete_selected_todo, "secondaryShellButton"))
    action_row.addWidget(shell_button(text.TODO_PREPARE_WORKSPACE, owner._workspace_from_selected_todo, "primaryShellButton"))
    layout.addLayout(action_row)
