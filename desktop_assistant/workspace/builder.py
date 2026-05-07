from __future__ import annotations

import re
from pathlib import Path

from ..activity import ActivitySnapshot
from ..adapters.windows_app_discovery import ApplicationInventoryStore
from ..models import ActionPlan, ActionStep, ActionType, RiskLevel
from ..projects.store import ProjectCatalogStore
from ..todo import TodoItem
from .models import WorkspaceResource, WorkspaceSuggestion


class WorkspaceSuggestionBuilder:
    """Build confirmable workspace suggestions from todos, goals, or current activity."""

    def __init__(
        self,
        *,
        app_inventory_store: ApplicationInventoryStore | None = None,
        project_catalog_store: ProjectCatalogStore | None = None,
    ) -> None:
        self.app_inventory_store = app_inventory_store or ApplicationInventoryStore()
        self.project_catalog_store = project_catalog_store or ProjectCatalogStore()

    def from_todo(self, todo: TodoItem, *, user_feedback: str = "") -> WorkspaceSuggestion:
        resources: list[WorkspaceResource] = []
        hint = todo.workspace
        resources.extend(_resources_from_targets("app", hint.apps, ActionType.OPEN_APP, "打开待办所需应用。"))
        resources.extend(_resources_from_targets("url", hint.urls, ActionType.OPEN_URL, "打开参考网页。"))
        resources.extend(_resources_from_targets("file", hint.files, ActionType.OPEN_FILE, "打开相关文件。"))
        resources.extend(_resources_from_targets("folder", hint.folders, ActionType.OPEN_FOLDER, "打开相关文件夹。"))
        resources.extend(_resources_from_targets("project", hint.projects, ActionType.OPEN_PROJECT, "打开相关项目。"))
        if not resources:
            resources.extend(self._goal_resources(_todo_resource_text(todo)))
        return self._build(
            goal=todo.title,
            title=f"工作区建议：{todo.title}",
            resources=resources,
            source="todo_workspace",
            user_feedback=user_feedback,
        )

    def from_goal(
        self,
        goal: str,
        *,
        activity: ActivitySnapshot | None = None,
        user_feedback: str = "",
    ) -> WorkspaceSuggestion:
        resources = []
        resources.extend(self._goal_resources(goal))
        if not resources and activity is not None:
            resources.extend(_resources_from_activity(activity))
        return self._build(
            goal=goal,
            title="工作环境建议",
            resources=resources,
            source="goal_workspace",
            user_feedback=user_feedback,
        )

    def continue_from_activity(self, activity: ActivitySnapshot) -> WorkspaceSuggestion:
        resources = _resources_from_activity(activity)
        label = activity.active_project.name if activity.active_project else "刚才的工作"
        return self._build(
            goal=f"继续：{label}",
            title="继续刚才的工作",
            resources=resources,
            source="activity_continue",
        )

    def refine(self, suggestion: WorkspaceSuggestion, user_feedback: str) -> WorkspaceSuggestion:
        feedback = user_feedback.strip()
        resources = list(suggestion.resources)
        resources.extend(self._goal_resources(feedback))
        refined = self._build(
            goal=suggestion.goal,
            title=suggestion.title,
            resources=resources,
            source=suggestion.source,
            user_feedback=feedback,
        )
        combined_feedback = list(suggestion.user_feedback)
        if feedback:
            combined_feedback.append(feedback)
        return refined.model_copy(
            update={
                "id": suggestion.id,
                "created_at": suggestion.created_at,
                "user_feedback": combined_feedback,
            },
            deep=True,
        )

    def _goal_resources(self, goal: str) -> list[WorkspaceResource]:
        resources: list[WorkspaceResource] = []
        for url in _urls(goal):
            resources.append(_resource("url", url, ActionType.OPEN_URL, "打开用户提到的网页。"))
        try:
            app = self.app_inventory_store.ensure(refresh=False).find(goal)
        except Exception:  # noqa: BLE001 - app inventory is optional context
            app = None
        if app is not None:
            resources.append(_resource("app", app.name, ActionType.OPEN_APP, "打开匹配到的本地应用。"))
        try:
            project = self.project_catalog_store.find(goal)
        except Exception:  # noqa: BLE001 - project catalog is optional context
            project = None
        if project is not None:
            resources.append(_resource("project", project.name, ActionType.OPEN_PROJECT, "打开匹配到的项目。"))
        if not resources:
            resources.extend(self._default_work_goal_resources(goal))
        return _dedupe(resources)

    def _default_work_goal_resources(self, goal: str) -> list[WorkspaceResource]:
        lowered = goal.lower()
        if not _looks_like_work_goal(lowered):
            return []
        app_names = _preferred_apps_for_goal(lowered)
        for app_name in app_names:
            try:
                app = self.app_inventory_store.ensure(refresh=False).find(app_name)
            except Exception:  # noqa: BLE001 - app inventory is optional context
                app = None
            if app is not None:
                return [_resource("app", app.name, ActionType.OPEN_APP, "打开适合这个目标的常用应用。")]
        return []

    def _build(
        self,
        *,
        goal: str,
        title: str,
        resources: list[WorkspaceResource],
        source: str,
        user_feedback: str = "",
    ) -> WorkspaceSuggestion:
        plan = ActionPlan(
            plan_name=source,
            source="workspace_suggestion",
            steps=[_action_step(resource) for resource in _dedupe(resources)],
        )
        feedback = [user_feedback.strip()] if user_feedback.strip() else []
        summary = "暂时没有明确动作。" if not plan.steps else f"建议执行 {len(plan.steps)} 个动作。"
        return WorkspaceSuggestion(
            goal=goal,
            title=title,
            summary=summary,
            resources=_dedupe(resources),
            plan=plan,
            source=source,
            user_feedback=feedback,
        )


def _resources_from_activity(activity: ActivitySnapshot) -> list[WorkspaceResource]:
    resources: list[WorkspaceResource] = []
    if activity.active_project:
        resources.append(_resource("project", activity.active_project.name, ActionType.OPEN_PROJECT, "重新打开项目。"))
    if activity.active_file and activity.active_file.path:
        resources.append(_resource("file", activity.active_file.path, ActionType.OPEN_FILE, "重新打开当前文件。"))
    if activity.active_app:
        resources.append(_resource("app", activity.active_app.name, ActionType.FOCUS_APP, "聚焦当前应用。"))
    return _dedupe(resources)


def _todo_resource_text(todo: TodoItem) -> str:
    parts = [
        todo.title,
        todo.description,
        todo.reminder_at or "",
        todo.due_at or "",
        todo.priority.value,
        "重要" if todo.is_important() else "",
    ]
    return "\n".join(part for part in parts if part)


def _resources_from_targets(kind: str, targets: list[str], action_type: ActionType, reason: str) -> list[WorkspaceResource]:
    return [_resource(kind, target, action_type, reason) for target in targets if target.strip()]


def _resource(kind: str, target: str, action_type: ActionType, reason: str) -> WorkspaceResource:
    title = Path(target).name if kind in {"file", "folder"} else target
    return WorkspaceResource(kind=kind, target=target, title=title, reason=reason, action_type=action_type.value)


def _action_step(resource: WorkspaceResource) -> ActionStep:
    return ActionStep(
        action_type=ActionType(resource.action_type),
        target=resource.target,
        risk_level=RiskLevel.LOW,
        reason=resource.reason,
    )


def _urls(value: str) -> list[str]:
    return re.findall(r"https?://[^\s，。；;]+", value)


def _looks_like_work_goal(value: str) -> bool:
    markers = ("写", "整理", "设计", "开发", "调试", "修改", "周报", "文档", "代码", "项目", "资料", "会议", "复盘")
    blockers = ("天气", "价格", "新闻", "查询", "搜索", "多少", "几号")
    return any(marker in value for marker in markers) and not any(blocker in value for blocker in blockers)


def _preferred_apps_for_goal(value: str) -> tuple[str, ...]:
    if any(marker in value for marker in ("代码", "开发", "调试", "ui", "项目")):
        return ("Cursor", "Visual Studio Code", "VS Code")
    if any(marker in value for marker in ("写", "周报", "文档", "报告", "复盘", "会议")):
        return ("Obsidian", "Microsoft Word", "Word", "Notion", "Cursor")
    return ("Cursor", "Obsidian", "Notion")


def _dedupe(resources: list[WorkspaceResource]) -> list[WorkspaceResource]:
    seen: set[tuple[str, str]] = set()
    deduped: list[WorkspaceResource] = []
    for resource in resources:
        key = (resource.action_type, resource.target.strip().lower())
        if resource.target.strip() and key not in seen:
            seen.add(key)
            deduped.append(resource)
    return deduped
