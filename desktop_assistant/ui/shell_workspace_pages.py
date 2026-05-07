from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QTextEdit, QVBoxLayout, QWidget

from . import shell_text as text
from .shell_page_helpers import page_header, section_label, shell_button, surface_card


def build_workspace_confirm_page(owner) -> QWidget:  # type: ignore[no-untyped-def]
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addLayout(page_header(text.WORKSPACE_CONFIRM_TITLE, owner._back_from_workspace_confirmation))
    preview_card, preview_layout = surface_card()
    preview_layout.addWidget(section_label(text.WORKSPACE_CONFIRM_TITLE))
    owner.workspace_confirm_text = QTextEdit()
    owner.workspace_confirm_text.setObjectName("workspaceConfirmText")
    owner.workspace_confirm_text.setReadOnly(True)
    owner.workspace_confirm_text.setPlainText(text.WORKSPACE_CONFIRM_EMPTY)
    preview_layout.addWidget(owner.workspace_confirm_text, stretch=1)
    layout.addWidget(preview_card, stretch=1)
    action_card, action_layout = surface_card()
    _add_confirmation_buttons(owner, action_layout)
    _add_remedy_buttons(owner, action_layout)
    layout.addWidget(action_card)
    owner._set_workspace_confirm_buttons(reject_enabled=False, run_enabled=False, trust_enabled=False)
    return page


def build_workspace_page(owner) -> QWidget:  # type: ignore[no-untyped-def]
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addLayout(page_header(text.WORKSPACE_TITLE, owner._show_menu))
    goal_card, goal_layout = surface_card()
    goal_layout.addWidget(section_label(text.WORKSPACE_TITLE))
    owner.workspace_input = QLineEdit()
    owner.workspace_input.setObjectName("workspaceInput")
    owner.workspace_input.setPlaceholderText(text.WORKSPACE_GOAL_PLACEHOLDER)
    goal_layout.addWidget(owner.workspace_input)
    _add_recipe_picker(owner, goal_layout)
    layout.addWidget(goal_card)

    result_card, result_layout = surface_card()
    result_layout.addWidget(section_label(text.WORKSPACE_RESULT_LEAD))
    owner.workspace_text = QTextEdit()
    owner.workspace_text.setObjectName("workspaceText")
    owner.workspace_text.setReadOnly(True)
    owner.workspace_text.setPlainText(text.WORKSPACE_EMPTY)
    result_layout.addWidget(owner.workspace_text, stretch=1)
    layout.addWidget(result_card, stretch=1)

    action_card, action_layout = surface_card()
    _add_workspace_action_editor(owner, action_layout)
    layout.addWidget(action_card)

    feedback_card, feedback_layout = surface_card()
    owner.feedback_input = QLineEdit()
    owner.feedback_input.setObjectName("feedbackInput")
    owner.feedback_input.setPlaceholderText(text.WORKSPACE_FEEDBACK_PLACEHOLDER)
    feedback_layout.addWidget(owner.feedback_input)
    _add_workspace_flow_buttons(owner, feedback_layout)
    layout.addWidget(feedback_card)
    return page


def _add_confirmation_buttons(owner, layout: QVBoxLayout) -> None:  # type: ignore[no-untyped-def]
    row = QHBoxLayout()
    owner.workspace_confirm_reject_button = shell_button(
        text.TODO_REJECT_WORKSPACE,
        owner._reject_confirmed_workspace,
        "secondaryShellButton",
    )
    owner.workspace_confirm_run_button = shell_button(
        text.TODO_RUN_WORKSPACE_ONCE,
        owner._run_confirmed_workspace_once,
        "primaryShellButton",
    )
    owner.workspace_confirm_trust_button = shell_button(
        text.TODO_TRUST_WORKSPACE,
        owner._trust_confirmed_workspace,
        "secondaryShellButton",
    )
    row.addWidget(owner.workspace_confirm_reject_button)
    row.addWidget(owner.workspace_confirm_run_button)
    row.addWidget(owner.workspace_confirm_trust_button)
    layout.addLayout(row)


def _add_remedy_buttons(owner, layout: QVBoxLayout) -> None:  # type: ignore[no-untyped-def]
    remedy_row = QHBoxLayout()
    owner.workspace_remedy_buttons = []
    for index in range(3):
        button = shell_button(
            "",
            lambda _checked=False, remedy_index=index: owner._run_workspace_remedy_index(remedy_index),
            "secondaryShellButton",
        )
        button.setVisible(False)
        owner.workspace_remedy_buttons.append(button)
        remedy_row.addWidget(button)
    layout.addLayout(remedy_row)


def _add_recipe_picker(owner, layout: QVBoxLayout) -> None:  # type: ignore[no-untyped-def]
    recipe_row = QHBoxLayout()
    owner.workspace_recipe_combo = QComboBox()
    owner.workspace_recipe_combo.setObjectName("workspaceRecipeCombo")
    recipe_row.addWidget(owner.workspace_recipe_combo, stretch=1)
    recipe_row.addWidget(shell_button(text.WORKSPACE_LOAD_RECIPE, owner._load_workspace_recipe, "secondaryShellButton"))
    layout.addLayout(recipe_row)


def _add_workspace_action_editor(owner, layout: QVBoxLayout) -> None:  # type: ignore[no-untyped-def]
    action_title = QLabel(text.WORKSPACE_ACTION_SECTION)
    action_title.setObjectName("smallNote")
    layout.addWidget(action_title)
    action_hint = QLabel(text.WORKSPACE_ACTION_SECTION_HINT)
    action_hint.setObjectName("smallNote")
    layout.addWidget(action_hint)
    owner.workspace_plan_action_list = QListWidget()
    owner.workspace_plan_action_list.setObjectName("workspaceActionList")
    owner.workspace_plan_action_list.setMaximumHeight(120)
    owner.workspace_plan_action_list.itemSelectionChanged.connect(owner._workspace_plan_action_selected)
    owner.workspace_plan_action_list.itemChanged.connect(lambda *_: owner._workspace_plan_actions_changed())
    layout.addWidget(owner.workspace_plan_action_list)

    target_row = QHBoxLayout()
    owner.workspace_plan_action_type_combo = QComboBox()
    owner.workspace_plan_action_type_combo.setObjectName("workspaceActionTypeCombo")
    for label, value in text.TODO_ACTION_TYPE_ITEMS:
        owner.workspace_plan_action_type_combo.addItem(label, value)
    owner.workspace_plan_action_target_input = QComboBox()
    owner.workspace_plan_action_target_input.setObjectName("workspaceActionTargetInput")
    owner.workspace_plan_action_target_input.setEditable(True)
    owner.workspace_plan_action_target_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    owner.workspace_plan_action_type_combo.currentIndexChanged.connect(
        lambda *_: owner._workspace_plan_action_type_changed()
    )
    target_row.addWidget(owner.workspace_plan_action_type_combo)
    target_row.addWidget(owner.workspace_plan_action_target_input, stretch=1)
    owner.workspace_plan_action_browse_button = shell_button(
        text.TODO_SELECT_TARGET,
        owner._browse_workspace_plan_action_target,
        "secondaryShellButton",
    )
    owner.workspace_plan_action_browse_button.setVisible(False)
    target_row.addWidget(owner.workspace_plan_action_browse_button)
    layout.addLayout(target_row)

    edit_buttons = QHBoxLayout()
    edit_buttons.addWidget(shell_button(text.TODO_ADD_WORKSPACE_ACTION, owner._add_workspace_plan_action, "secondaryShellButton"))
    edit_buttons.addWidget(shell_button(text.WORKSPACE_UPDATE_ACTION, owner._update_workspace_plan_action, "secondaryShellButton"))
    edit_buttons.addWidget(shell_button(text.WORKSPACE_REMOVE_ACTION, owner._remove_workspace_plan_action, "secondaryShellButton"))
    layout.addLayout(edit_buttons)


def _add_workspace_flow_buttons(owner, layout: QVBoxLayout) -> None:  # type: ignore[no-untyped-def]
    buttons = QHBoxLayout()
    buttons.addWidget(shell_button(text.WORKSPACE_GENERATE, owner._generate_workspace, "primaryShellButton"))
    buttons.addWidget(shell_button(text.WORKSPACE_REFINE, owner._refine_workspace, "secondaryShellButton"))
    buttons.addWidget(shell_button(text.WORKSPACE_SAVE_DRAFT, owner._save_workspace, "secondaryShellButton"))
    buttons.addWidget(shell_button(text.WORKSPACE_PLAN, owner._plan_workspace_goal, "primaryShellButton"))
    layout.addLayout(buttons)
