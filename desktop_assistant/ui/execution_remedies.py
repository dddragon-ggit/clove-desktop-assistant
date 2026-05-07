from __future__ import annotations

from dataclasses import dataclass, field

from ..models import ActionType, ExecutionDiagnosis, ExecutionStepResult, RiskLevel


@dataclass(frozen=True)
class ExecutionRemedy:
    """A user-facing recovery option after an action fails."""

    kind: str
    label: str
    description: str
    action_type: ActionType | None = None
    target: str = ""
    params: dict = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    delay_seconds: int = 0

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.kind, self.action_type.value if self.action_type else "", self.target)


def remedies_for_results(results: list[ExecutionStepResult], *, limit: int = 3) -> list[ExecutionRemedy]:
    remedies: list[ExecutionRemedy] = []
    seen: set[tuple[str, str, str]] = set()
    for result in results:
        for remedy in remedies_for_result(result):
            if remedy.key in seen:
                continue
            seen.add(remedy.key)
            remedies.append(remedy)
            if len(remedies) >= limit:
                return remedies
    return remedies


def remedies_for_result(result: ExecutionStepResult) -> list[ExecutionRemedy]:
    diagnosis = result.diagnosis
    if diagnosis is None:
        return []
    code = _display_code(diagnosis)
    target = _target_from_result(result)
    fallback_url = str(result.metadata.get("fallback_url") or diagnosis.details.get("fallback_url") or "")

    if code in {"APP_NOT_IN_INVENTORY", "APP_EXECUTABLE_MISSING"}:
        return [
            ExecutionRemedy(
                kind="refresh_app_inventory",
                label="刷新应用清单",
                description="重新扫描已安装应用，然后再尝试打开。",
            )
        ]
    if code in {"APP_PROCESS_RUNNING_NO_WINDOW", "APP_LAUNCH_NOT_VERIFIED", "APP_WINDOW_NOT_FOUND"}:
        return [
            ExecutionRemedy(
                kind="retry_focus_app",
                label="5秒后再聚焦",
                description="应用可能还在启动，稍等后重新查找窗口。",
                action_type=ActionType.FOCUS_APP,
                target=target,
                delay_seconds=5,
            )
        ]
    if code in {"WINDOW_NOT_FOUND", "WINDOW_ENUMERATION_FAILED"}:
        return [
            ExecutionRemedy(
                kind="refresh_windows",
                label="刷新窗口列表",
                description="重新读取当前桌面的可见窗口。",
                action_type=ActionType.LIST_WINDOWS,
                target="visible",
                params={"limit": 50},
            )
        ]
    if code in {"WEB_QUERY_NO_DIRECT_ANSWER", "WEB_QUERY_TRANSPORT_ERROR"} and fallback_url:
        return [
            ExecutionRemedy(
                kind="open_fallback_url",
                label="打开搜索页",
                description="直接打开搜索结果，方便你继续查看。",
                action_type=ActionType.OPEN_URL,
                target=fallback_url,
            )
        ]
    if code in {"FILE_NOT_FOUND", "FOLDER_NOT_FOUND", "PROJECT_NOT_FOUND"}:
        return [
            ExecutionRemedy(
                kind="select_path",
                label="重新选择路径",
                description="回到详情页，重新选择文件、文件夹或项目位置。",
                action_type=result.action.action_type,
                target=result.action.target,
            )
        ]
    if code == "HANDLER_NOT_REGISTERED":
        return [
            ExecutionRemedy(
                kind="open_capability_debug",
                label="查看能力状态",
                description="检查这个动作是否已经启用，并确认 handler 可用。",
                action_type=result.action.action_type,
                target=result.action.target,
            )
        ]
    return []


def remedy_lines(results: list[ExecutionStepResult]) -> list[str]:
    remedies = remedies_for_results(results)
    if not remedies:
        return []
    lines = ["", "可以继续："]
    lines.extend(f"- {remedy.label}：{remedy.description}" for remedy in remedies)
    return lines


def _display_code(diagnosis: ExecutionDiagnosis) -> str:
    if diagnosis.code == "CAPABILITY_VALIDATION_FAILED":
        issues = diagnosis.details.get("issues")
        if isinstance(issues, list) and issues:
            issue = issues[0]
            if isinstance(issue, dict) and issue.get("code"):
                return str(issue["code"])
    return diagnosis.code


def _target_from_result(result: ExecutionStepResult) -> str:
    if result.diagnosis is not None:
        for key in ("app_name", "target", "window_title", "url"):
            value = result.diagnosis.details.get(key)
            if value:
                return str(value)
    return result.action.target
