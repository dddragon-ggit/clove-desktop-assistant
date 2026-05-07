from __future__ import annotations

from pathlib import Path

from ..models import ActionStep
from ..workspace import WorkspaceSuggestion
from . import shell_text as text
from .localization import action_label, localized_text, risk_label


def workspace_suggestion_text(suggestion: WorkspaceSuggestion) -> str:
    lines = [
        text.WORKSPACE_RESULT_LEAD,
        "",
        f"{text.WORKSPACE_GOAL_LABEL}{suggestion.goal}",
    ]
    if suggestion.user_feedback:
        lines.append(f"{text.WORKSPACE_FEEDBACK_LABEL}{suggestion.user_feedback[-1]}")
    if not suggestion.plan.steps:
        lines.extend(["", text.WORKSPACE_NO_ACTIONS_DETAIL, text.WORKSPACE_REFINE_TIP])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            text.WORKSPACE_RESULT_COUNT.format(count=len(suggestion.plan.steps)),
            "",
            text.WORKSPACE_ACTIONS_LABEL,
        ]
    )
    for index, step in enumerate(suggestion.plan.steps, 1):
        lines.extend(_step_lines(index, step))
    lines.extend(["", "下一步：确认后我会逐项执行；想改方案，就在下方补一句要求。", text.WORKSPACE_REFINE_TIP, text.WORKSPACE_CONFIRM_TIP])
    return "\n".join(lines)


def compact_workspace_action_lines(suggestion: WorkspaceSuggestion | None) -> list[str]:
    if suggestion is None:
        return []
    return [
        f"{index}. {action_label(step.action_type.value)}：{_target_title(step)}"
        for index, step in enumerate(suggestion.plan.steps, 1)
    ]


def _step_lines(index: int, step: ActionStep) -> list[str]:
    label = action_label(step.action_type.value)
    title = _target_title(step)
    lines = [f"{index}. {label}：{title}"]
    if _show_raw_target(step, title):
        lines.append(f"   {text.WORKSPACE_ACTION_PATH}{step.target}")
    if step.reason:
        lines.append(f"   {text.WORKSPACE_ACTION_PURPOSE}{localized_text(step.reason)}")
    lines.append(f"   {text.WORKSPACE_ACTION_RISK}{risk_label(step.risk_level.value)}")
    return lines


def _target_title(step: ActionStep) -> str:
    if step.action_type.value in {"open_file", "open_folder", "open_project"}:
        name = Path(step.target).name
        return name or step.target
    return step.target


def _show_raw_target(step: ActionStep, title: str) -> bool:
    if step.action_type.value not in {"open_file", "open_folder", "open_project"}:
        return False
    return bool(step.target and step.target != title)
