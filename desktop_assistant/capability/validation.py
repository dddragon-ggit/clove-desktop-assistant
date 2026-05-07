from __future__ import annotations

from ..models import ActionStep, ActionType, PolicyIssue, RiskLevel


SHELL_LIKE_APP_MARKERS = (
    "powershell",
    "pwsh",
    "cmd.exe",
    "command prompt",
    "windows terminal",
    "wt.exe",
    "terminal.exe",
)


def validate_common(action: ActionStep) -> list[PolicyIssue]:
    if action.target.strip():
        return []
    return [
        PolicyIssue(
            code="TARGET_EMPTY",
            message=f"Action {action.action_type.value} needs a non-empty target.",
        )
    ]


def validate_open_url(action: ActionStep) -> list[PolicyIssue]:
    target = action.target.strip().lower()
    if target.startswith(("http://", "https://")):
        return []
    return [
        PolicyIssue(
            code="URL_SCHEME_NOT_ALLOWED",
            message="open_url only accepts http or https URLs.",
        )
    ]


def validate_open_app(action: ActionStep) -> list[PolicyIssue]:
    target = " ".join([action.target, str(action.params.get("executable_path", ""))]).lower()
    if not any(marker in target for marker in SHELL_LIKE_APP_MARKERS):
        return []
    return [
        PolicyIssue(
            code="APP_LAUNCH_BLOCKED",
            message="Shell-like applications are blocked by capability policy.",
        )
    ]


def validate_path_target(action: ActionStep) -> list[PolicyIssue]:
    target = action.target.strip()
    if "\x00" not in target:
        return []
    return [
        PolicyIssue(
            code="PATH_TARGET_INVALID",
            message=f"{action.action_type.value} target contains an invalid path character.",
        )
    ]


def max_risk(left: RiskLevel, right: RiskLevel) -> RiskLevel:
    return left if _risk_rank(left) >= _risk_rank(right) else right


def _risk_rank(level: RiskLevel) -> int:
    order = {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.CRITICAL: 3,
    }
    return order[level]
