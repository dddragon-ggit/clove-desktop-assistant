from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from ..models import ActionPlan, ActionStep, ActionType, RiskLevel
from ..workspace import WorkspaceResource, WorkspaceSuggestion
from .localization import action_label, localized_text


ACTION_ROLE = Qt.ItemDataRole.UserRole

ACTION_LABELS = {
    ActionType.OPEN_APP: "应用",
    ActionType.OPEN_URL: "网页",
    ActionType.OPEN_FILE: "文件",
    ActionType.OPEN_FOLDER: "文件夹",
    ActionType.OPEN_PROJECT: "项目",
    ActionType.FOCUS_APP: "聚焦应用",
}


def populate_action_list(widget: QListWidget, suggestion: WorkspaceSuggestion | None) -> None:
    widget.blockSignals(True)
    widget.clear()
    if suggestion is not None:
        for step in suggestion.plan.steps:
            add_action_item(widget, step)
    widget.blockSignals(False)


def add_action_item(widget: QListWidget, step: ActionStep) -> QListWidgetItem:
    item = QListWidgetItem(_item_text(step))
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
    item.setCheckState(Qt.CheckState.Checked)
    item.setData(ACTION_ROLE, step.model_dump(mode="json"))
    widget.addItem(item)
    return item


def append_action_from_input(widget: QListWidget, action_type: str, target: str) -> bool:
    clean_target = target.strip()
    if not clean_target:
        return False
    try:
        parsed_type = ActionType(action_type)
    except ValueError:
        return False
    add_action_item(
        widget,
        ActionStep(
            action_type=parsed_type,
            target=clean_target,
            risk_level=RiskLevel.LOW,
            reason="用户在工作区建议中手动添加。",
        ),
    )
    return True


def update_selected_action_from_input(widget: QListWidget, action_type: str, target: str) -> bool:
    item = widget.currentItem()
    clean_target = target.strip()
    if item is None or not clean_target:
        return False
    try:
        parsed_type = ActionType(action_type)
    except ValueError:
        return False
    step = ActionStep(
        action_type=parsed_type,
        target=clean_target,
        risk_level=RiskLevel.LOW,
        reason="用户调整了这个工作区动作。",
    )
    checked = item.checkState()
    item.setText(_item_text(step))
    item.setData(ACTION_ROLE, step.model_dump(mode="json"))
    item.setCheckState(checked)
    return True


def remove_selected_action(widget: QListWidget) -> bool:
    row = widget.currentRow()
    if row < 0:
        return False
    widget.takeItem(row)
    return True


def selected_action_plan(widget: QListWidget, base_plan: ActionPlan) -> ActionPlan:
    steps = []
    for index in range(widget.count()):
        item = widget.item(index)
        if item.checkState() != Qt.CheckState.Checked:
            continue
        payload = item.data(ACTION_ROLE)
        if isinstance(payload, dict):
            steps.append(ActionStep.model_validate(payload))
    return ActionPlan(plan_name=base_plan.plan_name, source=base_plan.source, steps=steps)


def edited_suggestion(suggestion: WorkspaceSuggestion | None, widget: QListWidget) -> WorkspaceSuggestion | None:
    if suggestion is None:
        return None
    plan = selected_action_plan(widget, suggestion.plan)
    existing = {
        (resource.action_type, resource.target.strip().lower()): resource
        for resource in suggestion.resources
    }
    resources = [
        existing.get((step.action_type.value, step.target.strip().lower())) or _resource_from_step(step)
        for step in plan.steps
    ]
    return suggestion.model_copy(
        update={
            "plan": plan,
            "resources": resources,
            "summary": "暂时没有明确动作。" if not plan.steps else f"最终选择 {len(plan.steps)} 个动作。",
        }
    )


def action_descriptions(widget: QListWidget) -> list[str]:
    descriptions = []
    for index in range(widget.count()):
        item = widget.item(index)
        mark = "✓" if item.checkState() == Qt.CheckState.Checked else "×"
        payload = item.data(ACTION_ROLE)
        if isinstance(payload, dict):
            action = ActionStep.model_validate(payload)
            descriptions.append(f"{mark} {action.action_type.value} -> {action.target}")
    return descriptions


def _item_text(step: ActionStep) -> str:
    label = action_label(step.action_type.value) or ACTION_LABELS.get(step.action_type, step.action_type.value)
    first = f"{label} · {step.target}"
    return f"{first}\n{localized_text(step.reason)}" if step.reason else first


def _resource_from_step(step: ActionStep) -> WorkspaceResource:
    return WorkspaceResource(
        kind=_resource_kind(step.action_type.value),
        target=step.target,
        title=step.target,
        reason=step.reason,
        action_type=step.action_type.value,
    )


def _resource_kind(action_type: str) -> str:
    return {
        "open_app": "app",
        "focus_app": "app",
        "open_url": "url",
        "open_file": "file",
        "open_folder": "folder",
        "open_project": "project",
    }.get(action_type, "other")
