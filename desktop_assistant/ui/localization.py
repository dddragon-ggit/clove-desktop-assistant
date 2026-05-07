from __future__ import annotations

import re


ACTION_LABELS = {
    "open_app": "打开应用",
    "focus_app": "聚焦应用",
    "list_windows": "列出窗口",
    "focus_window": "聚焦窗口",
    "minimize_window": "最小化窗口",
    "maximize_window": "最大化窗口",
    "restore_window": "恢复窗口",
    "close_window": "关闭窗口",
    "open_url": "打开网页",
    "open_project": "打开项目",
    "open_folder": "打开文件夹",
    "open_file": "打开文件",
    "answer_query": "查询并回答",
    "show_tasks": "显示待办",
    "restore_workspace": "恢复工作区",
    "create_reminder": "创建提醒",
    "start_focus_timer": "开始专注计时",
}

RISK_LABELS = {
    "low": "低风险",
    "medium": "中风险",
    "high": "高风险",
    "critical": "严重风险",
}

WORKFLOW_STATUS_LABELS = {
    "prepared": "已准备",
    "dry_run_ready": "预演完成",
    "partial": "部分完成",
    "completed": "已完成",
    "rejected": "已拒绝",
    "failed": "失败",
    "stopped": "已停止",
    "cancelled": "已取消",
}

EXECUTION_STATUS_LABELS = {
    "success": "成功",
    "partial": "部分完成",
    "failed": "失败",
    "skipped": "已跳过",
    "cancelled": "已取消",
    "pending": "等待中",
    "rejected": "已拒绝",
}

DECISION_STATE_LABELS = {
    "ready": "可执行",
    "needs_confirmation": "需要确认",
    "blocked": "已阻止",
    "executed": "已执行",
    "failed": "失败",
    "stopped": "已停止",
    "no_actions": "没有可执行动作",
}

PLAN_SOURCE_LABELS = {
    "fake_planner": "本地模拟规划器",
    "fake_planner_refinement": "本地模拟规划器调整",
    "provider_planner": "真实模型规划器",
    "inventory_fast_path": "本地应用快速路径",
    "model_inventory_path": "模型应用匹配路径",
    "workspace_suggestion": "工作区建议",
}

TIMING_LABELS = {
    "context_seconds": "上下文耗时",
    "prepare_seconds": "准备耗时",
    "planner_seconds": "规划耗时",
    "policy_seconds": "策略检查耗时",
    "reviewer_seconds": "审查耗时",
    "execution_seconds": "执行耗时",
}

TEXT_REPLACEMENTS = {
    "FakePlanner": "模拟规划器",
    "FakeReviewer": "模拟审查器",
    "Planner": "规划器",
    "Reviewer": "审查器",
    "Policy": "策略",
    "approved": "已通过",
    "blocked": "已阻止",
    "requires confirmation": "需要确认",
    "Sunday": "星期日",
    "Monday": "星期一",
    "Tuesday": "星期二",
    "Wednesday": "星期三",
    "Thursday": "星期四",
    "Friday": "星期五",
    "Saturday": "星期六",
}


def action_label(value: str) -> str:
    return ACTION_LABELS.get(value, value)


def risk_label(value: str) -> str:
    return RISK_LABELS.get(value, value)


def workflow_status_label(value: str) -> str:
    return WORKFLOW_STATUS_LABELS.get(value, value)


def execution_status_label(value: str | None) -> str:
    if not value:
        return ""
    return EXECUTION_STATUS_LABELS.get(value, value)


def decision_state_label(value: str) -> str:
    return DECISION_STATE_LABELS.get(value, value)


def plan_source_label(value: str) -> str:
    return PLAN_SOURCE_LABELS.get(value, value)


def timing_label(value: str) -> str:
    return TIMING_LABELS.get(value, value)


def bool_label(value: bool) -> str:
    return "是" if value else "否"


def approval_label(value: bool) -> str:
    return "已通过" if value else "已阻止"


def localized_text(value: str) -> str:
    text = value
    for source, replacement in TEXT_REPLACEMENTS.items():
        text = _replace_token(text, source, replacement)
    for source, replacement in ACTION_LABELS.items():
        text = _replace_token(text, source, replacement)
    for source, replacement in RISK_LABELS.items():
        text = _replace_token(text, source, replacement)
    return text


def _replace_token(text: str, source: str, replacement: str) -> str:
    return re.sub(rf"(?<![A-Za-z0-9_]){re.escape(source)}(?![A-Za-z0-9_])", replacement, text)
