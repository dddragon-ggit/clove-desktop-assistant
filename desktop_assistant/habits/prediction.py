from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..activity import ActivitySnapshot
from ..storage import quarantine_corrupted_file, write_json_atomic
from ..todo import TodoItem, build_home_status
from ..todo.models import TodoUrgency
from ..workspace import WorkspaceSuggestion
from .context import meaningful_snapshot, resume_text, same_meaningful_context
from .models import PREDICTION_SCHEMA_VERSION, NextActionPrediction
from .patterns import HabitPatternAnalyzer


def default_prediction_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "next_action_prediction.json"


class NextActionPredictionStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_prediction_path()

    def load(self) -> NextActionPrediction:
        if not self.path.exists():
            return NextActionPrediction.empty()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            quarantine_corrupted_file(self.path, source="prediction_store", category="prediction_store_corrupted", reason="Prediction JSON is unreadable.")
            return NextActionPrediction.empty()
        prediction = payload.get("prediction") if isinstance(payload, dict) else payload
        if not isinstance(prediction, dict):
            quarantine_corrupted_file(self.path, source="prediction_store", category="prediction_store_invalid", reason="Prediction JSON payload is invalid.")
            return NextActionPrediction.empty()
        try:
            return NextActionPrediction.model_validate(prediction)
        except Exception:
            quarantine_corrupted_file(self.path, source="prediction_store", category="prediction_store_invalid", reason="Prediction payload could not be validated.")
            return NextActionPrediction.empty()

    def save(self, prediction: NextActionPrediction) -> NextActionPrediction:
        payload = {
            "schema_version": PREDICTION_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "prediction": prediction.model_dump(mode="json"),
        }
        write_json_atomic(self.path, payload)
        return prediction


class NextActionPredictor:
    def predict(
        self,
        *,
        snapshot: ActivitySnapshot | None = None,
        todos: list[TodoItem] | None = None,
        activity_history: list[ActivitySnapshot] | None = None,
        pending_workspace: WorkspaceSuggestion | None = None,
        now: datetime | None = None,
    ) -> NextActionPrediction:
        open_todos = [item for item in todos or [] if item.is_open()]
        if open_todos:
            home = build_home_status(open_todos, now=now)
            if home.urgency in {TodoUrgency.RED, TodoUrgency.ORANGE} and home.next_task_title:
                prefix = "为待办准备工作区" if _todo_needs_workspace(open_todos, home.next_task_id) else "处理待办"
                return NextActionPrediction(
                    suggested_text=f"{prefix}：{home.next_task_title}",
                    route_hint="todo",
                    confidence="high",
                    source="urgent_todo",
                    target_id=home.next_task_id,
                    target_label=home.next_task_title,
                    reasons=[f"Nearest reminder is in {home.minutes_until_next} minutes."],
                )
        if pending_workspace is not None and pending_workspace.has_actions():
            return NextActionPrediction(
                suggested_text=f"继续确认工作区：{pending_workspace.title}",
                route_hint="workspace",
                confidence="high",
                source="pending_workspace",
                target_id=pending_workspace.id,
                target_label=pending_workspace.title,
                reasons=["A workspace suggestion is still pending confirmation."],
            )

        interrupted = _interrupted_snapshot(snapshot, activity_history or [])
        if interrupted is not None:
            return NextActionPrediction(
                suggested_text=resume_text(interrupted, interrupted=True),
                route_hint="continue_work",
                confidence="medium",
                source="interrupted_activity",
                target_label=resume_text(interrupted),
                reasons=["Recent meaningful activity differs from the current foreground context."],
            )

        current_time = now or datetime.now(UTC)
        habit = HabitPatternAnalyzer().predict_same_hour(
            records=activity_history or [],
            now=current_time,
            current_snapshot=snapshot,
        )
        if habit is not None:
            return NextActionPrediction(
                suggested_text=f"按习惯准备：{habit.label}",
                route_hint="continue_work",
                confidence=habit.confidence,
                source=habit.source,
                target_label=habit.label,
                reasons=[f"Seen {habit.count} time(s) around this hour recently."],
            )

        if meaningful_snapshot(snapshot):
            return NextActionPrediction(
                suggested_text=resume_text(snapshot),
                route_hint="continue_work",
                confidence="low",
                source="context_completion",
                target_label=resume_text(snapshot),
                reasons=["The current project/file can complete a vague 'continue' command."],
            )
        return NextActionPrediction(
            suggested_text="查看待办任务清单",
            route_hint="todo",
            confidence="low",
            source="fallback",
            reasons=["No stronger activity or task signal is available."],
        )


def _todo_needs_workspace(items: list[TodoItem], item_id: str | None) -> bool:
    for item in items:
        if item.id == item_id:
            hint = item.workspace
            return item.needs_computer or any([hint.apps, hint.urls, hint.files, hint.folders, hint.projects])
    return False


def _interrupted_snapshot(
    current: ActivitySnapshot | None,
    history: list[ActivitySnapshot],
) -> ActivitySnapshot | None:
    records = [record for record in history if meaningful_snapshot(record)]
    records.sort(key=_captured_timestamp, reverse=True)
    for record in records:
        if same_meaningful_context(current, record):
            return None
        return record
    return None


def _captured_timestamp(snapshot: ActivitySnapshot) -> float:
    try:
        return datetime.fromisoformat(snapshot.captured_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
