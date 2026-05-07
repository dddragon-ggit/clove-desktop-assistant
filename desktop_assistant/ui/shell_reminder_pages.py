from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from ..todo import ReminderSettings
from ..todo.models import TodoPriority, TodoTaskType
from ..todo.reminder_settings import default_reminder_policy, reminder_policy_key
from . import shell_text as text
from .shell_page_helpers import page_header, section_label, shell_button, surface_card


def build_reminder_settings_page(owner) -> QWidget:  # type: ignore[no-untyped-def]
    page = QWidget()
    page_layout = QVBoxLayout(page)
    page_layout.setContentsMargins(0, 0, 0, 0)
    page_layout.setSpacing(8)
    page_layout.addLayout(page_header(text.REMINDER_SETTINGS_TITLE, owner._show_todo_page))

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    quiet_card, quiet_layout = surface_card()
    quiet_layout.addWidget(section_label(text.REMINDER_SETTINGS_QUIET_SECTION))
    owner.reminder_quiet_enabled_check = QCheckBox(text.REMINDER_SETTINGS_QUIET_ENABLED)
    owner.reminder_quiet_enabled_check.setObjectName("smallNote")
    quiet_layout.addWidget(owner.reminder_quiet_enabled_check)
    quiet_row = QHBoxLayout()
    owner.reminder_quiet_start_input = QLineEdit()
    owner.reminder_quiet_start_input.setPlaceholderText("23:00")
    owner.reminder_quiet_end_input = QLineEdit()
    owner.reminder_quiet_end_input.setPlaceholderText("07:00")
    owner.reminder_daily_reset_spin = QSpinBox()
    owner.reminder_daily_reset_spin.setRange(0, 23)
    owner.reminder_daily_reset_spin.setSuffix(text.REMINDER_SETTINGS_HOUR_SUFFIX)
    quiet_row.addWidget(QLabel(text.REMINDER_SETTINGS_QUIET_START))
    quiet_row.addWidget(owner.reminder_quiet_start_input)
    quiet_row.addWidget(QLabel(text.REMINDER_SETTINGS_QUIET_END))
    quiet_row.addWidget(owner.reminder_quiet_end_input)
    quiet_row.addWidget(QLabel(text.REMINDER_SETTINGS_DAILY_RESET))
    quiet_row.addWidget(owner.reminder_daily_reset_spin)
    quiet_layout.addLayout(quiet_row)
    hint = QLabel(text.REMINDER_SETTINGS_QUIET_HINT)
    hint.setObjectName("smallNote")
    hint.setWordWrap(True)
    quiet_layout.addWidget(hint)
    layout.addWidget(quiet_card)

    policy_card, policy_layout = surface_card()
    policy_layout.addWidget(section_label(text.REMINDER_SETTINGS_POLICY_SECTION))
    policy_hint = QLabel(text.REMINDER_SETTINGS_POLICY_HINT)
    policy_hint.setObjectName("smallNote")
    policy_hint.setWordWrap(True)
    policy_layout.addWidget(policy_hint)
    grid = QGridLayout()
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(6)
    headers = [
        text.REMINDER_SETTINGS_TASK_TYPE,
        text.REMINDER_SETTINGS_PRIORITY,
        "重复提醒",
        text.REMINDER_SETTINGS_REPEAT_MINUTES,
        text.REMINDER_SETTINGS_MAX_REPEATS,
        text.REMINDER_SETTINGS_SNOOZE_MINUTES,
    ]
    for column, header in enumerate(headers):
        label = QLabel(header)
        label.setObjectName("smallNote")
        grid.addWidget(label, 0, column)

    owner.reminder_policy_controls = {}
    row = 1
    for task_type in [TodoTaskType.TEMPORARY, TodoTaskType.DAILY]:
        for priority in [TodoPriority.LOW, TodoPriority.NORMAL, TodoPriority.HIGH, TodoPriority.URGENT]:
            key = reminder_policy_key(task_type, priority)
            enabled = QCheckBox()
            repeat_minutes = _spinbox(1, 1440, text.REMINDER_SETTINGS_MINUTE_SUFFIX)
            max_repeats = _spinbox(0, 20, "")
            snooze_minutes = _spinbox(1, 1440, text.REMINDER_SETTINGS_MINUTE_SUFFIX)
            grid.addWidget(QLabel(_task_type_label(task_type)), row, 0)
            grid.addWidget(QLabel(_priority_label(priority)), row, 1)
            grid.addWidget(enabled, row, 2)
            grid.addWidget(repeat_minutes, row, 3)
            grid.addWidget(max_repeats, row, 4)
            grid.addWidget(snooze_minutes, row, 5)
            owner.reminder_policy_controls[key] = {
                "enabled": enabled,
                "repeat_minutes": repeat_minutes,
                "max_repeats": max_repeats,
                "snooze_minutes": snooze_minutes,
            }
            row += 1
    policy_layout.addLayout(grid)
    layout.addWidget(policy_card)

    action_card, action_layout = surface_card()
    action_row = QHBoxLayout()
    action_row.addWidget(shell_button(text.REMINDER_SETTINGS_SAVE, owner._save_reminder_settings, "primaryShellButton"))
    action_row.addWidget(shell_button(text.REMINDER_SETTINGS_RESET_DEFAULTS, owner._reset_reminder_settings_defaults, "secondaryShellButton"))
    owner.reminder_settings_feedback = QLabel("")
    owner.reminder_settings_feedback.setObjectName("smallNote")
    action_row.addWidget(owner.reminder_settings_feedback, stretch=1)
    action_layout.addLayout(action_row)
    layout.addWidget(action_card)

    scroll.setWidget(content)
    page_layout.addWidget(scroll, stretch=1)
    return page


def populate_reminder_settings(owner, settings: ReminderSettings) -> None:  # type: ignore[no-untyped-def]
    owner.reminder_quiet_enabled_check.setChecked(settings.quiet_enabled)
    owner.reminder_quiet_start_input.setText(settings.quiet_start)
    owner.reminder_quiet_end_input.setText(settings.quiet_end)
    owner.reminder_daily_reset_spin.setValue(settings.daily_reset_hour)
    for task_type in TodoTaskType:
        for priority in TodoPriority:
            key = reminder_policy_key(task_type, priority)
            policy = settings.policies.get(key) or default_reminder_policy(task_type, priority)
            controls = owner.reminder_policy_controls[key]
            controls["enabled"].setChecked(policy.enabled and policy.repeat_enabled)
            controls["repeat_minutes"].setValue(policy.repeat_minutes)
            controls["max_repeats"].setValue(policy.max_repeats)
            controls["snooze_minutes"].setValue(policy.snooze_minutes)


def collect_reminder_settings(owner) -> ReminderSettings:  # type: ignore[no-untyped-def]
    policies = {}
    for task_type in TodoTaskType:
        for priority in TodoPriority:
            key = reminder_policy_key(task_type, priority)
            controls = owner.reminder_policy_controls[key]
            enabled = controls["enabled"].isChecked()
            policies[key] = {
                "enabled": True,
                "repeat_enabled": enabled,
                "repeat_minutes": controls["repeat_minutes"].value(),
                "max_repeats": controls["max_repeats"].value() if enabled else 0,
                "snooze_minutes": controls["snooze_minutes"].value(),
            }
    return ReminderSettings(
        quiet_enabled=owner.reminder_quiet_enabled_check.isChecked(),
        quiet_start=owner.reminder_quiet_start_input.text().strip() or "23:00",
        quiet_end=owner.reminder_quiet_end_input.text().strip() or "07:00",
        daily_reset_hour=owner.reminder_daily_reset_spin.value(),
        policies=policies,
    )


def _spinbox(minimum: int, maximum: int, suffix: str) -> QSpinBox:
    widget = QSpinBox()
    widget.setRange(minimum, maximum)
    if suffix:
        widget.setSuffix(suffix)
    return widget


def _task_type_label(task_type: TodoTaskType) -> str:
    return text.TODO_DAILY_TASK if task_type == TodoTaskType.DAILY else text.TODO_TEMPORARY_TASK


def _priority_label(priority: TodoPriority) -> str:
    labels = {value: label for label, value in text.TODO_PRIORITY_ITEMS}
    return labels.get(priority.value, priority.value)
