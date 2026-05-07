from __future__ import annotations

import json

from ..action_trust import TrustedActionRule
from ..models import ActionStep
from ..projects import ProjectLocation
from ..recipe import WorkflowRecipe
from .localization import action_label, localized_text, risk_label


def trusted_action_label(rule: TrustedActionRule) -> str:
    return f"{rule.action_type} -> {rule.target} [{rule.risk_level}]"


def trusted_action_detail_text(rule: TrustedActionRule) -> str:
    return "\n".join(
        [
            f"Trusted action: {rule.action_type}",
            f"Target: {rule.target}",
            f"Risk: {rule.risk_level}",
            f"Key: {rule.key}",
            f"Created: {rule.created_at}",
            f"Note: {rule.note or '-'}",
            "",
            "Params",
            json.dumps(rule.params, ensure_ascii=False, indent=2),
        ]
    )


def recipe_label(recipe: WorkflowRecipe) -> str:
    check = "未检查"
    if recipe.last_check is not None:
        check = "可用" if recipe.last_check.ok else f"{len(recipe.last_check.issues)} 个问题"
    return (
        f"{recipe.name} | {risk_label(recipe.risk_level.value)} | "
        f"{len(recipe.plan.steps)} 个动作 | {check}"
    )


def recipe_detail_text(recipe: WorkflowRecipe) -> str:
    lines = [
        f"方案：{recipe.name}",
        f"目标：{recipe.user_goal}",
        f"风险：{risk_label(recipe.risk_level.value)}",
        f"场景：{recipe.scenario or '未分类'}",
        f"说明：{recipe.description or '-'}",
        f"动作数：{len(recipe.plan.steps)}",
        f"更新：{recipe.updated_at}",
        f"调整次数：{len(recipe.revision_history)}",
        f"最近检查：{recipe.last_check.checked_at if recipe.last_check else '未检查'}",
        f"最近运行：{recipe.last_run_status or '-'}",
        f"运行反馈：{localized_text(recipe.last_run_message or '-')}",
        "",
        "执行内容",
    ]
    if recipe.plan.steps:
        for index, step in enumerate(recipe.plan.steps, start=1):
            lines.append(_recipe_step_line(index, step))
    else:
        lines.append("暂时没有动作。")
    lines.append("")
    lines.append("调整记录")
    if recipe.revision_history:
        for index, revision in enumerate(recipe.revision_history[-5:], start=1):
            refinement = f" | 用户补充：{revision.user_refinement}" if revision.user_refinement else ""
            lines.append(
                f"{index}. {revision.created_at} | {revision.plan_name} | "
                f"{revision.action_count} 个动作 | {localized_text(revision.note)}{refinement}"
            )
    else:
        lines.append("暂无调整。")
    lines.append("")
    lines.append("静态检查")
    if recipe.last_check is None:
        lines.append("还没有检查。")
    elif not recipe.last_check.issues:
        lines.append("可用。")
    else:
        lines.append(f"是否可用：{'是' if recipe.last_check.ok else '否'}")
        for issue in recipe.last_check.issues:
            step = f"第 {issue.step_index + 1} 步：" if issue.step_index is not None else ""
            lines.append(f"- {issue.severity} {issue.code}: {step}{issue.message}")
    return "\n".join(lines)


def _recipe_step_line(index: int, step: ActionStep) -> str:
    reason = f" · {localized_text(step.reason)}" if step.reason else ""
    return (
        f"{index}. {action_label(step.action_type.value)}：{step.target} "
        f"({risk_label(step.risk_level.value)}){reason}"
    )


def project_label(location: ProjectLocation) -> str:
    return f"{location.name} | {location.kind}"


def project_detail_text(location: ProjectLocation) -> str:
    return "\n".join(
        [
            f"Project: {location.name}",
            f"Kind: {location.kind}",
            f"Path: {location.path}",
            f"Description: {location.description or '-'}",
        ]
    )
