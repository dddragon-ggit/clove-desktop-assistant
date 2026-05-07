from __future__ import annotations

from ..habits import NextActionPrediction
from .models import InputRoute, InputRouteType


TODO_MARKERS = ("待办", "任务", "提醒", "todo", "清单", "完成", "新增", "添加", "删除", "改")
WORKSPACE_MARKERS = ("工作环境", "工作区", "环境", "开始工作", "打开这些", "方案", "配方")
CONTINUE_MARKERS = ("继续", "刚才", "上次", "恢复", "回到")
WORK_GOAL_MARKERS = ("写", "整理", "设计", "开发", "调试", "修改", "周报", "文档", "代码", "项目", "资料", "会议", "复盘")
DIRECT_WORKSPACE_MARKERS = (
    "打开",
    "启动",
    "运行",
    "聚焦",
    "切到",
    "进入",
    "准备",
    "open ",
    "launch ",
    "start ",
    "focus ",
)


class InputRouter:
    """Route the compact home input into a product surface."""

    def route(
        self,
        text: str,
        *,
        prediction: NextActionPrediction | None = None,
        accepted_prediction: bool = False,
    ) -> InputRoute:
        raw = text.strip()
        if accepted_prediction and prediction and prediction.suggested_text:
            return InputRoute(
                route_type=_route_type(prediction.route_hint),
                normalized_text=prediction.suggested_text,
                confidence=prediction.confidence,
                source="accepted_prediction",
                accepted_prediction=True,
                target_id=prediction.target_id,
                reason="User accepted the grey prediction with Tab.",
            )
        if not raw and prediction and prediction.suggested_text:
            return InputRoute(
                route_type=_route_type(prediction.route_hint),
                normalized_text=prediction.suggested_text,
                confidence="low",
                source="empty_input_prediction",
                target_id=prediction.target_id,
                reason="No text was entered; prediction is available as a hint.",
            )
        lowered = raw.lower()
        if _contains(lowered, TODO_MARKERS):
            return _route(InputRouteType.TODO, raw, "medium", "todo keyword")
        if _contains(lowered, WORKSPACE_MARKERS):
            return _route(InputRouteType.WORKSPACE, raw, "medium", "workspace keyword")
        if _looks_like_work_goal(lowered):
            return _route(InputRouteType.WORKSPACE, raw, "medium", "work goal keyword")
        if _contains(lowered, CONTINUE_MARKERS):
            if _is_vague_continue(raw) and prediction and prediction.suggested_text:
                return InputRoute(
                    route_type=_route_type(prediction.route_hint),
                    normalized_text=prediction.suggested_text,
                    confidence=prediction.confidence,
                    source="context_prediction",
                    target_id=prediction.target_id,
                    reason="Vague continue input was completed by the current prediction.",
                )
            return _route(InputRouteType.CONTINUE_WORK, raw, "medium", "continue keyword")
        if _contains(lowered, DIRECT_WORKSPACE_MARKERS):
            return _route(InputRouteType.WORKSPACE, raw, "medium", "direct workspace action")
        return _route(InputRouteType.DIALOG, raw, "low", "fallback to conversation")


def _route(route_type: InputRouteType, text: str, confidence: str, reason: str) -> InputRoute:
    return InputRoute(route_type=route_type, normalized_text=text, confidence=confidence, reason=reason)


def _contains(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker.lower() in text for marker in markers)


def _looks_like_work_goal(text: str) -> bool:
    if _contains(text, ("天气", "价格", "新闻", "查询", "搜索", "几号", "多少", "百科")):
        return False
    return _contains(text, WORK_GOAL_MARKERS)


def _is_vague_continue(text: str) -> bool:
    normalized = "".join(char for char in text.strip().lower() if char.isalnum())
    return normalized in {"继续", "继续一下", "恢复", "恢复刚才", "刚才", "上次", "回到刚才"}


def _route_type(value: str) -> InputRouteType:
    try:
        return InputRouteType(value)
    except ValueError:
        return InputRouteType.DIALOG
