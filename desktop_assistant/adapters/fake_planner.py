from __future__ import annotations

from ..models import ActionPlan, ActionStep, ActionType, ContextSnapshot, PlannerResult, RiskLevel, WorkflowRequest
from .fake_planner_rules import (
    _looks_unsafe_request,
    _requested_app_target,
    _requested_focus_target,
    _requested_lookup_query,
    _requested_project_target,
    _requested_replacement_target,
    _requested_website_url,
    _requested_window_action,
)


class FakePlanner:
    """Deterministic planner used before real model integration."""

    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        if request.plan_refinement is not None:
            return _refined_fake_plan(request, context)

        text = request.user_request.strip()
        lowered = text.lower()
        website_url = _requested_website_url(text)
        lookup_query = _requested_lookup_query(text)
        window_action = _requested_window_action(text)
        focus_target = _requested_focus_target(text)
        project_target = _requested_project_target(text)
        app_target = _requested_app_target(text)

        if _looks_unsafe_request(text):
            steps = []
            plan_name = "unsafe-needs-clarification"
            risk_guess = RiskLevel.HIGH
            requires_clarification = True
        elif window_action is not None:
            action_type, target = window_action
            risk = RiskLevel.MEDIUM if action_type == ActionType.CLOSE_WINDOW else RiskLevel.LOW
            steps = [
                ActionStep(
                    action_type=action_type,
                    target=target,
                    risk_level=risk,
                    reason="根据窗口标题或应用名管理现有桌面窗口。",
                )
            ]
            plan_name = "window-state-management"
            risk_guess = risk
            requires_clarification = False
        elif focus_target is not None:
            steps = [
                ActionStep(
                    action_type=ActionType.FOCUS_APP,
                    target=focus_target,
                    risk_level=RiskLevel.LOW,
                    reason="切换到已打开的应用窗口。",
                )
            ]
            plan_name = "focus-app"
            risk_guess = RiskLevel.LOW
            requires_clarification = False
        elif project_target is not None:
            steps = [
                ActionStep(
                    action_type=ActionType.OPEN_PROJECT,
                    target=project_target,
                    risk_level=RiskLevel.LOW,
                    reason="从项目/常用文件夹目录中定位并打开。",
                )
            ]
            plan_name = "open-project"
            risk_guess = RiskLevel.LOW
            requires_clarification = False
        elif app_target is not None:
            steps = [
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target=app_target,
                    risk_level=RiskLevel.LOW,
                    reason="打开用户指定的本地应用。",
                )
            ]
            plan_name = "open-app"
            risk_guess = RiskLevel.LOW
            requires_clarification = False
        elif website_url is not None:
            steps = [
                ActionStep(
                    action_type=ActionType.OPEN_URL,
                    target=website_url,
                    risk_level=RiskLevel.LOW,
                    reason="打开用户指定网页。",
                )
            ]
            plan_name = "open-website"
            risk_guess = RiskLevel.LOW
            requires_clarification = False
        elif lookup_query is not None:
            steps = [
                ActionStep(
                    action_type=ActionType.ANSWER_QUERY,
                    target=lookup_query,
                    risk_level=RiskLevel.LOW,
                    reason="联网查询并在助手界面返回提炼后的结果。",
                )
            ]
            plan_name = "web-lookup"
            risk_guess = RiskLevel.LOW
            requires_clarification = False
        elif "周报" in text:
            steps = [
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Notion",
                    risk_level=RiskLevel.LOW,
                    reason="周报通常在 Notion 中整理。",
                ),
                ActionStep(
                    action_type=ActionType.OPEN_FOLDER,
                    target="D:/Work/Screenshots",
                    risk_level=RiskLevel.LOW,
                    reason="周报需要引用本周截图素材。",
                ),
                ActionStep(
                    action_type=ActionType.OPEN_URL,
                    target="https://example.com/dashboard",
                    risk_level=RiskLevel.LOW,
                    reason="查看本周数据看板。",
                ),
            ]
            plan_name = "weekly-report-setup"
            risk_guess = RiskLevel.MEDIUM
            requires_clarification = False
        elif "写作" in text or "write" in lowered:
            steps = [
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target="Obsidian",
                    risk_level=RiskLevel.LOW,
                    reason="写作模式默认使用 Obsidian。",
                ),
                ActionStep(
                    action_type=ActionType.OPEN_FOLDER,
                    target="D:/Notes/References",
                    risk_level=RiskLevel.LOW,
                    reason="写作需要参考资料目录。",
                ),
                ActionStep(
                    action_type=ActionType.START_FOCUS_TIMER,
                    target="25m",
                    params={"minutes": 25},
                    risk_level=RiskLevel.LOW,
                    reason="开始一段专注时间。",
                ),
            ]
            plan_name = "writing-setup"
            risk_guess = RiskLevel.LOW
            requires_clarification = False
        else:
            steps = [
                ActionStep(
                    action_type=ActionType.SHOW_TASKS,
                    target="today",
                    risk_level=RiskLevel.LOW,
                    reason="先展示今日相关任务。",
                ),
                ActionStep(
                    action_type=ActionType.CREATE_REMINDER,
                    target="10m",
                    params={"minutes": 10},
                    risk_level=RiskLevel.LOW,
                    reason="若暂不处理，则保留一个后续提醒。",
                ),
            ]
            plan_name = "generic-assistant-flow"
            risk_guess = RiskLevel.LOW
            requires_clarification = False

        return PlannerResult(
            intent_summary=f"根据请求“{request.user_request}”生成的结构化动作计划。",
            requires_clarification=requires_clarification,
            action_plan=ActionPlan(plan_name=plan_name, source="fake_planner", steps=steps),
            risk_guess=risk_guess,
            reasoning_summary=f"FakePlanner 基于当前上下文 {context.local_time} 生成固定可调试计划。",
        )


def _refined_fake_plan(request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
    refinement = request.plan_refinement
    if refinement is None:
        raise ValueError("plan_refinement is required for refined fake plan.")
    text = refinement.user_refinement.strip()
    lowered = text.lower()
    steps = [step.model_copy(deep=True) for step in refinement.current_plan.steps]

    if any(marker in lowered for marker in ["不要打开浏览器", "别打开浏览器", "without browser", "no browser"]):
        steps = [step for step in steps if step.action_type != ActionType.OPEN_URL]
    if any(marker in lowered for marker in ["不要打开网页", "别打开网页", "without web"]):
        steps = [step for step in steps if step.action_type != ActionType.OPEN_URL]

    replacement = _requested_replacement_target(text)
    if replacement:
        replaced = False
        for step in steps:
            if step.action_type in {ActionType.OPEN_APP, ActionType.FOCUS_APP}:
                step.target = replacement
                step.params = {}
                step.reason = f"Refined per user request: use {replacement}."
                replaced = True
                break
        if not replaced:
            steps.insert(
                0,
                ActionStep(
                    action_type=ActionType.OPEN_APP,
                    target=replacement,
                    risk_level=RiskLevel.LOW,
                    reason=f"Refined per user request: use {replacement}.",
                ),
            )

    if not steps:
        steps = [
            ActionStep(
                action_type=ActionType.SHOW_TASKS,
                target="draft",
                risk_level=RiskLevel.LOW,
                reason="No executable steps remained after refinement; keep the draft inspectable.",
            )
        ]

    risk = RiskLevel.LOW
    for step in steps:
        if step.risk_level in {RiskLevel.CRITICAL, RiskLevel.HIGH}:
            risk = step.risk_level
            break
        if step.risk_level == RiskLevel.MEDIUM:
            risk = RiskLevel.MEDIUM

    return PlannerResult(
        intent_summary=(
            f"Refined draft for '{refinement.original_goal}' using user change: {refinement.user_refinement}"
        ),
        requires_clarification=False,
        action_plan=ActionPlan(
            plan_name=f"{refinement.current_plan.plan_name}-refined",
            source="fake_planner_refinement",
            steps=steps,
        ),
        risk_guess=risk,
        reasoning_summary=(
            f"FakePlanner refined revision {refinement.revision_index} at {context.local_time}."
        ),
    )
