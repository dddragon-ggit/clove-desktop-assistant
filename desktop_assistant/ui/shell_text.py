from __future__ import annotations

from collections.abc import Iterable


APP_TITLE = "Desktop Assistant"
BACK_HOME = "首页"
MINIMIZE = "−"
CLOSE = "×"
BACK = "‹"

MENU_TITLE = "你想从哪里开始？"
MENU_TODO = "待办任务清单"
MENU_WORKSPACE = "工作环境选择"
MENU_CONTINUE = "继续刚才的工作"
CONTINUE_FALLBACK = "继续"

PREDICTION_PLACEHOLDER = "输入任何想法、目标或待办"

TODO_TITLE = "待办任务"
TODO_LIST_HINT = "点击某个待办查看详情和工作区建议。"
TODO_ADD_PLACEHOLDER = "新增待办"
TODO_QUICK_ADD_PLACEHOLDER = "快速记录一个待办"
TODO_DESCRIPTION_PLACEHOLDER = "说明，可留空"
TODO_TIME_PLACEHOLDER = "提醒时间，例如 18:30 / 明天 09:00 / 30m"
TODO_IMPORTANT = "重要"
TODO_NEEDS_COMPUTER = "电脑完成"
TODO_ADD = "添加"
TODO_SAVE_CHANGES = "保存"
TODO_CANCEL_ITEM = "取消待办"
TODO_COMPLETE = "完成"
TODO_DELETE = "删除"
TODO_POSTPONE = "推迟30分"
TODO_SKIP_TODAY = "今日跳过"
TODO_PREPARE_WORKSPACE = "现在准备"
TODO_REJECT_WORKSPACE = "拒绝"
TODO_RUN_WORKSPACE_ONCE = "本次执行"
TODO_TRUST_WORKSPACE = "永久确认"
TODO_ACTION_TARGET_PLACEHOLDER = "添加动作目标，例如 Cursor 或 https://example.com"
TODO_ADD_WORKSPACE_ACTION = "加入"
TODO_SAVE_WORKSPACE_BINDING = "保存绑定"
TODO_DETAIL_EMPTY = "选择一个待办后，我会在这里准备工作区建议。"
TODO_DETAIL_NO_ACTIONS = "暂未匹配到可直接执行的应用、网页、文件或项目。"
TODO_UNSCHEDULED = "待安排"
TODO_DETAIL_OVERVIEW = "任务概览"
TODO_DETAIL_WORKSPACE = "这个任务建议先这样准备："
TODO_DETAIL_NEXT_STEP = "下一步"
TODO_DETAIL_NEXT_STEP_HINT = "可以先点“现在准备”，确认后由助手打开需要的应用、网页或文件；做完后点“完成”，暂时不做就推迟。"
TODO_DETAIL_READY_HINT = "点“现在准备”可以先确认再执行；不合适就取消勾选或补充动作。"
TODO_CONFIRMATION = "执行前会确认：{actions} 个动作，{risk}。"
TODO_CONFIRMATION_BLOCKED = "确认：策略未通过，不能执行。"
TODO_EXECUTING_WORKSPACE = "正在执行这个待办的工作区动作。"
TODO_EXECUTION_REJECTED = "已拒绝执行这个待办的工作区动作。"
TODO_EXECUTION_RESULT = "执行结果：{status}\n{message}"
TODO_FINAL_ACTIONS = "最终动作：\n{actions}"
TODO_CHANGES_SAVED = "已保存修改。"
TODO_CANCELLED = "已取消这个待办。"
TODO_DELETED = "已删除这个待办。"
TODO_DELETE_FAILED = "没有找到这个待办，可能已经被删除。"
TODO_ADDED = "已添加：{title}"
TODO_ADD_FAILED = "添加待办失败：{error}"
TODO_EMPTY_TITLE = "待办标题不能为空。"
TODO_WORKSPACE_BINDING_SAVED = "已保存工作区绑定。"
TODO_POSTPONED = "已稍后提醒。"
TODO_SKIPPED_TODAY = "已跳过今天。"
REMINDER_KIND_DUE = "提醒"
REMINDER_KIND_MISSED = "错过提醒"
REMINDER_KIND_REPEAT = "还没完成吗"
REMINDER_KIND_SNOOZED = "稍后提醒"
TODO_ACTION_APP_PLACEHOLDER = "输入或选择应用，例如 Cursor"
TODO_ACTION_FILE_PLACEHOLDER = "点击选择文件，或粘贴完整路径"
TODO_ACTION_FOLDER_PLACEHOLDER = "点击选择文件夹，或粘贴完整路径"
TODO_SELECT_TARGET = "选择"
TODO_SELECT_FILE = "选择文件"
TODO_SELECT_FOLDER = "选择文件夹"
TODO_SELECT_FILE_TITLE = "选择要加入工作区的文件"
TODO_SELECT_FOLDER_TITLE = "选择要加入工作区的文件夹"
TODO_PRIORITY_ITEMS = (
    ("普通", "normal"),
    ("低", "low"),
    ("重要", "high"),
    ("紧急", "urgent"),
)
TODO_TASK_TYPE_ITEMS = (
    ("临时任务", "temporary"),
    ("每日日常", "daily"),
)
TODO_DAILY_DONE_TODAY = "今日已完成"
TODO_TEMPORARY_TASK = "临时任务"
TODO_DAILY_TASK = "每日日常"

TODO_ACTION_TYPE_ITEMS = (
    ("应用", "open_app"),
    ("网页", "open_url"),
    ("文件", "open_file"),
    ("文件夹", "open_folder"),
    ("项目", "open_project"),
)

WORKSPACE_TITLE = "工作区建议"
WORKSPACE_GOAL_PLACEHOLDER = "你接下来想做什么？例如：继续 UI 设计 / 写周报 / 查资料"
WORKSPACE_EMPTY = "告诉我目标后，我会先准备一个可确认的工作区方案。"
WORKSPACE_FEEDBACK_PLACEHOLDER = "补充要求，例如：不要打开网页，再加项目文档"
WORKSPACE_GENERATE = "生成建议"
WORKSPACE_REFINE = "按意见调整"
WORKSPACE_SAVE_DRAFT = "保存方案"
WORKSPACE_PLAN = "确认执行"
WORKSPACE_DRAFT_SAVED = "\n已保存为待确认工作区草稿。"
WORKSPACE_RECIPE_PICKER_PLACEHOLDER = "选择已有工作区方案"
WORKSPACE_LOAD_RECIPE = "加载方案"
WORKSPACE_RECIPE_SAVED = "\n已保存为可复用方案：{name}"
WORKSPACE_RECIPE_LOADED = "\n已加载方案：{name}"
WORKSPACE_RECIPE_LOAD_FAILED = "\n没有找到这个工作区方案。"
WORKSPACE_NO_ACTIONS = "暂未匹配到可直接执行的应用、网页、文件或项目。"
WORKSPACE_RESULT_LEAD = "我建议先这样准备："
WORKSPACE_GOAL_LABEL = "目标："
WORKSPACE_FEEDBACK_LABEL = "已按你的补充调整："
WORKSPACE_RESULT_COUNT = "会准备 {count} 个动作，执行前仍会让你确认。"
WORKSPACE_ACTIONS_LABEL = "准备内容："
WORKSPACE_ACTION_PURPOSE = "用途："
WORKSPACE_ACTION_PATH = "位置："
WORKSPACE_ACTION_RISK = "风险："
WORKSPACE_NO_ACTIONS_DETAIL = "我还没有找到可以直接准备的应用、网页、文件或项目。"
WORKSPACE_REFINE_TIP = "想改的话，可以直接补充一句你的要求。"
WORKSPACE_CONFIRM_TIP = "确认后，我会按动作逐项执行。"
WORKSPACE_NEEDS_MORE_DETAIL = "这个方案还没有可执行动作，请先补充要打开的应用、网页、文件或项目。"
WORKSPACE_ACTION_SECTION = "方案动作"
WORKSPACE_ACTION_SECTION_HINT = "勾选要执行的动作，也可以新增或修改选中的动作。"
WORKSPACE_UPDATE_ACTION = "更新选中"
WORKSPACE_REMOVE_ACTION = "删除选中"
WORKSPACE_CONFIRM_TITLE = "执行前确认"
WORKSPACE_CONFIRM_EMPTY = "还没有可确认的工作区动作。"
WORKSPACE_CONFIRM_READY = "本次准备 {count} 个动作，整体风险：{risk}。"
WORKSPACE_CONFIRM_BLOCKED = "策略未通过，本次不能执行。"
WORKSPACE_CONFIRM_REQUIRES = "需要确认"
WORKSPACE_CONFIRM_TRUSTED = "已信任"
WORKSPACE_CONFIRM_AUTO = "无需确认"
WORKSPACE_GROUP_APPS = "应用"
WORKSPACE_GROUP_URLS = "网页"
WORKSPACE_GROUP_FILES = "文件"
WORKSPACE_GROUP_FOLDERS = "文件夹"
WORKSPACE_GROUP_PROJECTS = "项目"
WORKSPACE_GROUP_OTHER = "其他"

PROVIDER_TITLE = "模型设置"
PROVIDER_NAME_PLACEHOLDER = "名称，例如 OpenAI / Mimo"
PROVIDER_BASE_URL_PLACEHOLDER = "API 地址，例如 https://api.openai.com"
PROVIDER_API_KEY_PLACEHOLDER = "API Key"
PROVIDER_MODEL_PLACEHOLDER = "主模型，例如 gpt-4o"
PROVIDER_REVIEW_MODEL_PLACEHOLDER = "审查模型（可与主模型相同）"
PROVIDER_WIRE_API_LABEL = "接口格式"
PROVIDER_WIRE_API_RESPONSES = "OpenAI Responses"
PROVIDER_WIRE_API_ANTHROPIC = "Anthropic Messages"
PROVIDER_AUTO_DETECT = "自动检测"
PROVIDER_SAVE = "保存设置"
PROVIDER_TEST = "测试连接"
PROVIDER_SAVED = "已保存模型设置。"
PROVIDER_SAVE_FAILED = "保存失败：{error}"
PROVIDER_TEST_OK = "连接成功：{wire_api}"
PROVIDER_TEST_FAIL = "连接失败：{error}"
PROVIDER_CURRENT = "当前配置"

CHAT_TITLE = "对话与规划"
CHAT_RUN_ONCE = "执行一次"
CHAT_PLANNING = "正在规划，请稍等。"
CHAT_EXECUTING = "正在执行已确认动作。"


def home_count_text(important: int, total: int) -> str:
    return f"重要待办 {important} 件，全部待办 {total} 件"


def next_task_text(title: str | None, minutes: int | None) -> str:
    if not title:
        return "暂时没有带时间的待办。"
    suffix = f"{minutes} 分钟后" if minutes is not None else "待安排"
    return f"最近：{title} · {suffix}"


def priority_label(priority: str, *, important: bool = False) -> str:
    labels = {
        "low": "低",
        "normal": "普通",
        "high": "重要",
        "urgent": "紧急",
    }
    if important and priority not in {"high", "urgent"}:
        return "重要"
    return labels.get(priority, priority or "普通")


def todo_time_parse_error(value: str) -> str:
    return f"未识别提醒时间：{value}\n可使用 18:30、明天 09:00、30m。"


def todo_confirmation_text(*, approved: bool, action_count: int, risk: str) -> str:
    if not approved:
        return TODO_CONFIRMATION_BLOCKED
    return TODO_CONFIRMATION.format(actions=action_count, risk=risk)


def todo_list_text(*, title: str, priority: str, important: bool, next_time: str | None) -> str:
    prefix = f"{priority_label(priority, important=important)} · " if important or priority != "normal" else ""
    lines = [f"{prefix}{title}"]
    if next_time:
        lines.append(next_time)
    return "\n".join(lines)


def workspace_preview_text(title: str, summary: str, actions: Iterable[str]) -> str:
    lines = [title, summary, ""]
    action_lines = list(actions)
    lines.extend(action_lines or [WORKSPACE_NO_ACTIONS])
    return "\n".join(lines)


def todo_detail_text(
    *,
    title: str,
    priority: str,
    time_text: str | None,
    description: str,
    actions: Iterable[str],
    execution_message: str = "",
    workspace_sentence: str = "",
) -> str:
    lines = [
        TODO_DETAIL_OVERVIEW,
        f"任务：{title}",
        f"优先级：{priority} · 时间：{time_text or TODO_UNSCHEDULED}",
    ]
    if description:
        lines.append(f"说明：{description}")
    if execution_message:
        lines.extend(["", execution_message])
    lines.extend(["", TODO_DETAIL_WORKSPACE])
    if workspace_sentence:
        lines.append(workspace_sentence)
    action_lines = list(actions)
    if action_lines:
        lines.extend(action_lines)
        lines.append(TODO_DETAIL_READY_HINT)
    else:
        lines.append(TODO_DETAIL_NO_ACTIONS)
    lines.extend(["", TODO_DETAIL_NEXT_STEP, TODO_DETAIL_NEXT_STEP_HINT])
    return "\n".join(lines)


TODO_REMINDER_SETTINGS = "提醒设置"
REMINDER_SETTINGS_TITLE = "提醒设置"
REMINDER_SETTINGS_QUIET_SECTION = "全局静默与每日重置"
REMINDER_SETTINGS_QUIET_ENABLED = "启用静默时间"
REMINDER_SETTINGS_QUIET_START = "开始"
REMINDER_SETTINGS_QUIET_END = "结束"
REMINDER_SETTINGS_DAILY_RESET = "每日任务重置"
REMINDER_SETTINGS_HOUR_SUFFIX = " 点"
REMINDER_SETTINGS_MINUTE_SUFFIX = " 分钟"
REMINDER_SETTINGS_QUIET_HINT = "静默时间内不弹托盘通知和桌宠气泡；每日任务会按重置时间判断“今天”。"
REMINDER_SETTINGS_POLICY_SECTION = "按任务类型和优先级设置提醒方式"
REMINDER_SETTINGS_POLICY_HINT = "勾选表示未完成时会重复提醒；取消勾选仍保留到点提醒，但不会反复催。"
REMINDER_SETTINGS_TASK_TYPE = "类型"
REMINDER_SETTINGS_PRIORITY = "优先级"
REMINDER_SETTINGS_ENABLED = "重复"
REMINDER_SETTINGS_REPEAT_MINUTES = "间隔"
REMINDER_SETTINGS_MAX_REPEATS = "次数"
REMINDER_SETTINGS_SNOOZE_MINUTES = "稍后"
REMINDER_SETTINGS_SAVE = "保存提醒设置"
REMINDER_SETTINGS_RESET_DEFAULTS = "恢复默认"
REMINDER_SETTINGS_SAVED = "已保存提醒设置。"
REMINDER_SETTINGS_RESET = "已恢复默认提醒设置。"
