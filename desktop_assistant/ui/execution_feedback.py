from __future__ import annotations

import re

from ..models import ActionStep, ExecutionDiagnosis, ExecutionStatus, ExecutionStepResult
from .execution_remedies import remedy_lines
from .localization import action_label, execution_status_label, localized_text


TITLE_BY_STATUS = {
    "success": "执行完成",
    "partial": "部分完成",
    "failed": "没有完成",
    "skipped": "没有执行",
    "rejected": "已取消执行",
}

SUCCESS_TEXT = {
    "open_app": "已打开应用",
    "focus_app": "已聚焦应用",
    "list_windows": "已刷新窗口列表",
    "focus_window": "已聚焦窗口",
    "minimize_window": "已最小化窗口",
    "maximize_window": "已最大化窗口",
    "restore_window": "已恢复窗口",
    "close_window": "已请求关闭窗口",
    "open_url": "已打开网页",
    "open_project": "已打开项目",
    "open_folder": "已打开文件夹",
    "open_file": "已打开文件",
    "answer_query": "已完成查询",
    "show_tasks": "已显示待办",
    "restore_workspace": "已恢复工作区",
    "create_reminder": "已创建提醒",
    "start_focus_timer": "已开始专注计时",
}


def workspace_execution_feedback(results: list[ExecutionStepResult], *, status: str | None = None) -> str:
    if not results:
        return "没有执行动作。\n这次方案里没有可执行的工作区步骤。"
    final_status = status or _overall_status(results)
    title = TITLE_BY_STATUS.get(final_status, execution_status_label(final_status) or final_status)
    lines = [title, ""]
    for result in results:
        lines.append(_result_line(result))
        lines.extend(_success_detail_lines(result))
    failure = next((result for result in results if result.diagnosis is not None), None)
    if failure and failure.diagnosis:
        lines.extend(_diagnosis_lines(failure))
    lines.extend(remedy_lines(results))
    return "\n".join(line for line in lines if line is not None).strip()


def exception_feedback(message: str) -> str:
    first_line = _clean_message(message).splitlines()[0].strip() if message.strip() else "未知异常"
    return "\n".join(
        [
            "执行过程中出现异常。",
            first_line,
            "可以稍后重试；如果反复出现，需要查看完整错误堆栈。",
        ]
    )


def _overall_status(results: list[ExecutionStepResult]) -> str:
    statuses = {result.status for result in results}
    if statuses == {ExecutionStatus.SUCCESS}:
        return "success"
    if statuses == {ExecutionStatus.SKIPPED}:
        return "skipped"
    if ExecutionStatus.FAILED in statuses and ExecutionStatus.SUCCESS in statuses:
        return "partial"
    if ExecutionStatus.FAILED in statuses:
        return "failed"
    return "partial"


def _result_line(result: ExecutionStepResult) -> str:
    status = result.status
    if status == ExecutionStatus.SUCCESS:
        return _success_line(result.action)
    if status == ExecutionStatus.SKIPPED:
        return f"已跳过：{_action_target(result.action)}"
    if status == ExecutionStatus.CANCELLED:
        return f"已取消：{_action_target(result.action)}"
    if status == ExecutionStatus.PENDING:
        return f"仍在等待：{_action_target(result.action)}"
    return f"未完成：{_action_target(result.action)}"


def _success_line(action: ActionStep) -> str:
    verb = SUCCESS_TEXT.get(action.action_type.value, f"已完成{action_label(action.action_type.value)}")
    if action.action_type.value == "list_windows":
        return verb
    return f"{verb}：{action.target}"


def _success_detail_lines(result: ExecutionStepResult) -> list[str]:
    if result.status != ExecutionStatus.SUCCESS:
        return []
    if result.action.action_type.value == "list_windows":
        return _window_list_detail_lines(result)
    if result.action.action_type.value in {"focus_window", "minimize_window", "maximize_window", "restore_window", "close_window"}:
        return _window_action_detail_lines(result)
    if result.action.action_type.value != "answer_query":
        return []
    answer = str(result.metadata.get("answer") or "").strip()
    if not answer:
        return []
    lines = [f"查询结果：{answer}"]
    confidence = _confidence_text(str(result.metadata.get("confidence") or ""))
    reason = str(result.metadata.get("confidence_reason") or "").strip()
    if confidence:
        lines.append(f"可信度：{confidence}{f' · {reason}' if reason else ''}")
    verification = _query_verification_label(str(result.metadata.get("verification_status") or ""))
    if verification:
        lines.append(f"验证状态：{verification}")
    source_summary = str(result.metadata.get("source_summary") or "").strip()
    if source_summary:
        lines.append(f"来源概况：{source_summary}")
    sources = [str(source) for source in result.metadata.get("sources", []) if str(source).strip()]
    if sources:
        lines.append("来源：")
        lines.extend(f"- {source}" for source in sources[:3])
    fallback = str(result.metadata.get("fallback_url") or "").strip()
    if fallback and str(result.metadata.get("confidence")) in {"low", "none"}:
        lines.append(f"兜底搜索：{fallback}")
    return lines


def _window_list_detail_lines(result: ExecutionStepResult) -> list[str]:
    lines = []
    count = result.metadata.get("count")
    if count is not None:
        lines.append(f"可见窗口：{count} 个")
    foreground = result.metadata.get("foreground_window")
    if isinstance(foreground, dict) and foreground.get("title"):
        lines.append(f"当前前台：{foreground['title']}")
    windows = result.metadata.get("windows")
    if isinstance(windows, list) and windows:
        titles = [str(item.get("title")) for item in windows[:3] if isinstance(item, dict) and item.get("title")]
        if titles:
            lines.append("前几个窗口：" + "、".join(titles))
    return lines


def _window_action_detail_lines(result: ExecutionStepResult) -> list[str]:
    status = str(result.metadata.get("verification_status") or "")
    label = _verification_label(status)
    lines = [f"状态确认：{label}"] if label else []
    verified = result.metadata.get("verified_window")
    if isinstance(verified, dict):
        state = _window_state_text(verified)
        if state:
            lines.append(f"窗口状态：{state}")
    foreground = result.metadata.get("foreground_window")
    if isinstance(foreground, dict) and foreground.get("title"):
        lines.append(f"当前前台：{foreground['title']}")
    return lines


def _confidence_text(value: str) -> str:
    return {
        "high": "高",
        "medium": "中",
        "low": "低",
        "none": "无直接结论",
    }.get(value, value)


def _query_verification_label(value: str) -> str:
    return {
        "structured_source": "结构化来源",
        "multi_source_summary": "多来源摘要",
        "single_direct_source": "单一直接来源",
        "single_snippet_source": "单一网页摘要",
        "no_direct_source": "没有直接来源",
    }.get(value, "")


def _verification_label(value: str) -> str:
    return {
        "foreground_confirmed": "已确认窗口在前台",
        "foreground_different": "动作已发出，但当前前台是其他窗口",
        "foreground_unknown": "动作已发出，暂时无法确认前台窗口",
        "minimized_confirmed": "已确认窗口最小化",
        "minimized_unconfirmed": "动作已发出，但窗口状态尚未变为最小化",
        "maximized_confirmed": "已确认窗口最大化",
        "maximized_unconfirmed": "动作已发出，但窗口状态尚未变为最大化",
        "restored_confirmed": "已确认窗口恢复为普通状态",
        "restored_unconfirmed": "动作已发出，但窗口状态尚未恢复",
        "close_no_visible_window": "关闭请求已发出，窗口已不在可见列表中",
        "close_requested": "关闭请求已发出，应用可能还在确认是否退出",
        "window_missing_after_operation": "动作已发出，但窗口已不在可见列表中",
        "operation_requested": "动作已发出",
    }.get(value, "")


def _window_state_text(window: dict) -> str:
    states = []
    if window.get("is_minimized"):
        states.append("已最小化")
    if window.get("is_maximized"):
        states.append("已最大化")
    if not states:
        states.append("普通窗口")
    title = str(window.get("title") or "").strip()
    return f"{title}（{'，'.join(states)}）" if title else "，".join(states)


def _action_target(action: ActionStep) -> str:
    label = action_label(action.action_type.value)
    return f"{label}「{action.target}」" if action.target else label


def _diagnosis_lines(result: ExecutionStepResult) -> list[str]:
    diagnosis = result.diagnosis
    if diagnosis is None:
        return []
    code = _display_code(diagnosis)
    message = _friendly_failure(result.action, diagnosis, code)
    lines = ["", message]
    remedy = _friendly_remedy(diagnosis, code)
    if remedy:
        lines.append(remedy)
    lines.append(f"原因代码：{code}")
    return lines


def _display_code(diagnosis: ExecutionDiagnosis) -> str:
    if diagnosis.code == "CAPABILITY_VALIDATION_FAILED":
        issues = diagnosis.details.get("issues")
        if isinstance(issues, list) and issues:
            issue = issues[0]
            if isinstance(issue, dict) and issue.get("code"):
                return str(issue["code"])
    return diagnosis.code


def _friendly_failure(action: ActionStep, diagnosis: ExecutionDiagnosis, code: str) -> str:
    target = _target_from_details(action, diagnosis)
    path = str(diagnosis.details.get("path") or diagnosis.details.get("executable_path") or target)
    messages = {
        "APP_NOT_IN_INVENTORY": f"没有在应用清单里找到「{target}」。",
        "APP_EXECUTABLE_MISSING": f"找到了「{target}」的应用记录，但可执行文件已经不存在。",
        "APP_EXECUTABLE_NOT_ABSOLUTE": f"「{target}」的可执行文件路径不是完整路径。",
        "APP_EXECUTABLE_NOT_EXE": f"「{target}」的启动目标不是 Windows 可执行文件。",
        "APP_LAUNCH_BLOCKED": f"「{target}」像命令行或系统外壳，当前安全策略不允许直接启动。",
        "APP_PROCESS_RUNNING_NO_WINDOW": f"「{target}」的进程已经在运行，但暂时没有找到可操作窗口。",
        "APP_LAUNCH_NOT_VERIFIED": f"已尝试启动「{target}」，但还没有确认窗口出现。",
        "APP_WINDOW_NOT_FOUND": f"没有找到「{target}」的可见窗口。",
        "APP_FOCUS_REJECTED": f"Windows 拒绝把「{target}」切到前台。",
        "WINDOW_MANAGER_UNAVAILABLE": "当前环境暂时不能读取或控制窗口。",
        "WINDOW_ENUMERATION_FAILED": "读取当前窗口列表失败。",
        "WINDOW_LOOKUP_FAILED": f"查找窗口「{target}」时失败。",
        "WINDOW_NOT_FOUND": f"没有找到匹配「{target}」的窗口。",
        "WINDOW_OPERATION_REJECTED": f"Windows 拒绝执行这个窗口操作：{target}。",
        "BROWSER_OPEN_REJECTED": f"浏览器没有接受这个网页地址：{target}。",
        "URL_SCHEME_NOT_ALLOWED": f"这个网页地址的协议不在允许范围内：{target}。",
        "FOLDER_NOT_FOUND": f"没有找到文件夹：{path}。",
        "FILE_NOT_FOUND": f"没有找到文件：{path}。",
        "PROJECT_NOT_FOUND": f"没有找到项目或文件夹：{path}。",
        "TARGET_NOT_FOLDER": f"目标不是文件夹：{path}。",
        "TARGET_NOT_FILE": f"目标不是文件：{path}。",
        "HANDLER_NOT_REGISTERED": f"「{action_label(action.action_type.value)}」还没有接上真实执行能力。",
        "QUERY_EMPTY": "查询内容为空。",
        "WEB_QUERY_TRANSPORT_ERROR": "联网查询时请求失败。",
        "WEB_QUERY_NO_DIRECT_ANSWER": "联网查询没有拿到可直接展示的答案。",
    }
    if code in messages:
        return messages[code]
    return localized_text(_clean_message(diagnosis.message))


def _friendly_remedy(diagnosis: ExecutionDiagnosis, code: str) -> str:
    remedies = {
        "APP_NOT_IN_INVENTORY": "可以刷新应用清单，或确认应用已经安装。",
        "APP_EXECUTABLE_MISSING": "可以刷新应用清单，或重新安装/手动修正应用路径。",
        "APP_PROCESS_RUNNING_NO_WINDOW": "可以稍等几秒后再聚焦，或手动从托盘、登录页、更新页打开窗口。",
        "APP_LAUNCH_NOT_VERIFIED": "可以稍等几秒后重试，或检查是否卡在登录、更新、权限确认界面。",
        "APP_WINDOW_NOT_FOUND": "可以先打开应用，再尝试聚焦窗口。",
        "WINDOW_MANAGER_UNAVAILABLE": "请在同一个 Windows 桌面会话里运行助手，并确认 pywin32 可用。",
        "WINDOW_ENUMERATION_FAILED": "请确认助手和目标应用处于同一桌面会话和相近权限级别。",
        "WINDOW_NOT_FOUND": "可以先刷新窗口列表，或换一个更接近窗口标题的关键词。",
        "BROWSER_OPEN_REJECTED": "请检查默认浏览器是否可用。",
        "URL_SCHEME_NOT_ALLOWED": "请改用 http 或 https 地址。",
        "FOLDER_NOT_FOUND": "请检查路径是否存在，或重新选择文件夹。",
        "FILE_NOT_FOUND": "请检查路径是否存在，或重新选择文件。",
        "PROJECT_NOT_FOUND": "可以把项目加入项目目录，或重新选择项目文件夹。",
        "HANDLER_NOT_REGISTERED": "可以在能力目录里启用对应 handler，或换成已支持的动作。",
    }
    if code in remedies:
        return remedies[code]
    if diagnosis.remedy:
        return localized_text(_clean_message(diagnosis.remedy))
    return ""


def _target_from_details(action: ActionStep, diagnosis: ExecutionDiagnosis) -> str:
    for key in ("app_name", "target", "url"):
        value = diagnosis.details.get(key)
        if value:
            return str(value)
    return action.target


def _clean_message(value: str) -> str:
    text = re.sub(r"\[[^\]]+\]\s*", "", value).strip()
    return text.replace(" -> ", " ")
