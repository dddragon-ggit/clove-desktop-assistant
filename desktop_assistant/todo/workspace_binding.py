from __future__ import annotations

from ..models import ActionPlan, ActionType
from .models import TodoWorkspaceHint


def workspace_hint_from_plan(plan: ActionPlan) -> TodoWorkspaceHint:
    apps: list[str] = []
    urls: list[str] = []
    files: list[str] = []
    folders: list[str] = []
    projects: list[str] = []
    for step in plan.steps:
        if step.action_type in {ActionType.OPEN_APP, ActionType.FOCUS_APP}:
            _add_unique(apps, step.target)
        elif step.action_type == ActionType.OPEN_URL:
            _add_unique(urls, step.target)
        elif step.action_type == ActionType.OPEN_FILE:
            _add_unique(files, step.target)
        elif step.action_type == ActionType.OPEN_FOLDER:
            _add_unique(folders, step.target)
        elif step.action_type == ActionType.OPEN_PROJECT:
            _add_unique(projects, step.target)
    return TodoWorkspaceHint(apps=apps, urls=urls, files=files, folders=folders, projects=projects)


def workspace_hint_has_targets(hint: TodoWorkspaceHint) -> bool:
    return bool(hint.apps or hint.urls or hint.files or hint.folders or hint.projects)


def _add_unique(values: list[str], value: str) -> None:
    clean = value.strip()
    if clean and clean not in values:
        values.append(clean)
