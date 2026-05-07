from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from desktop_assistant.activity import ActivityApp, ActivityFile, ActivityProject, ActivitySnapshot
from desktop_assistant.activity import ActivityPrivacySettings, ActivityPrivacyStore, ActivityStore, apply_activity_privacy
from desktop_assistant.habits import (
    ActivitySamplingService,
    DailyActivityJournal,
    HabitTracker,
    NextActionPredictionStore,
    NextActionPredictor,
)
from desktop_assistant.models import ActionPlan, ActionStep, ActionType
from desktop_assistant.todo import TodoItem
from desktop_assistant.todo import TodoStore
from desktop_assistant.workspace import WorkspaceSuggestion


def _workspace_path() -> Path:
    base = Path.cwd() / "runtime" / "test_habits"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


class HabitJournalTests(unittest.TestCase):
    def test_daily_journal_appends_metadata_line_and_prunes_old_files(self) -> None:
        root = _workspace_path()
        try:
            journal = DailyActivityJournal(root)
            snapshot = ActivitySnapshot(
                captured_at="2026-04-30T09:20:00+00:00",
                active_app=ActivityApp(name="Cursor"),
                active_file=ActivityFile(name="main.py", path=r"D:\repo\main.py"),
                active_project=ActivityProject(name="repo", path=r"D:\repo"),
            )
            path = journal.append_snapshot(snapshot)
            journal.append_snapshot(snapshot)

            content = path.read_text(encoding="utf-8")
            self.assertEqual(content.count("app=Cursor"), 1)

            old_path = root / "2026-04-01.md"
            old_path.write_text("old", encoding="utf-8")
            deleted = journal.prune_old(keep_days=14, now=datetime(2026, 4, 30, tzinfo=UTC))

            self.assertIn(old_path, deleted)
            self.assertFalse(old_path.exists())
        finally:
            rmtree(root, ignore_errors=True)


class NextActionPredictionTests(unittest.TestCase):
    def test_predictor_prefers_urgent_todo_over_activity(self) -> None:
        now = datetime(2026, 4, 30, 9, 0, tzinfo=UTC)
        todo = TodoItem(title="提交报告", reminder_at=(now + timedelta(minutes=10)).isoformat())
        snapshot = ActivitySnapshot(active_project=ActivityProject(name="demo", path=r"D:\demo"))

        prediction = NextActionPredictor().predict(snapshot=snapshot, todos=[todo], now=now)

        self.assertEqual(prediction.route_hint, "todo")
        self.assertIn("提交报告", prediction.suggested_text)
        self.assertEqual(prediction.confidence, "high")

    def test_predictor_prefers_pending_workspace_after_urgent_todo(self) -> None:
        suggestion = WorkspaceSuggestion(
            goal="写周报",
            title="周报工作区",
            plan=ActionPlan(
                plan_name="workspace",
                source="test",
                steps=[ActionStep(action_type=ActionType.OPEN_APP, target="Cursor")],
            ),
        )

        prediction = NextActionPredictor().predict(
            snapshot=ActivitySnapshot(active_project=ActivityProject(name="demo", path=r"D:\demo")),
            todos=[],
            pending_workspace=suggestion,
        )

        self.assertEqual(prediction.source, "pending_workspace")
        self.assertEqual(prediction.route_hint, "workspace")
        self.assertIn("周报工作区", prediction.suggested_text)

    def test_predictor_recovers_interrupted_meaningful_activity(self) -> None:
        interrupted = ActivitySnapshot(
            captured_at=datetime(2026, 4, 30, 8, 50, tzinfo=UTC).isoformat(),
            active_file=ActivityFile(name="app.py", path=r"D:\repo\desktop_assistant\ui\app.py"),
            active_project=ActivityProject(name="desktop_assistant", path=r"D:\repo\desktop_assistant"),
        )

        prediction = NextActionPredictor().predict(
            snapshot=ActivitySnapshot(active_app=ActivityApp(name="QQ")),
            todos=[],
            activity_history=[interrupted],
        )

        self.assertEqual(prediction.source, "interrupted_activity")
        self.assertEqual(prediction.route_hint, "continue_work")
        self.assertIn("恢复中断：desktop_assistant 的 UI 设计", prediction.suggested_text)

    def test_predictor_uses_same_hour_habit_when_not_current_context(self) -> None:
        now = datetime(2026, 4, 30, 9, 0, tzinfo=UTC)
        habit_a = ActivitySnapshot(
            captured_at=datetime(2026, 4, 28, 9, 10, tzinfo=UTC).isoformat(),
            active_project=ActivityProject(name="project_a", path=r"D:\project_a"),
        )
        habit_b = ActivitySnapshot(
            captured_at=datetime(2026, 4, 29, 9, 20, tzinfo=UTC).isoformat(),
            active_project=ActivityProject(name="project_a", path=r"D:\project_a"),
        )
        current = ActivitySnapshot(
            captured_at=now.isoformat(),
            active_project=ActivityProject(name="project_b", path=r"D:\project_b"),
        )

        prediction = NextActionPredictor().predict(
            snapshot=current,
            todos=[],
            activity_history=[habit_a, habit_b, current],
            now=now,
        )

        self.assertEqual(prediction.source, "habit_time")
        self.assertEqual(prediction.confidence, "medium")
        self.assertEqual(prediction.suggested_text, "按习惯准备：project_a")

    def test_predictor_completes_vague_continue_with_current_project_focus(self) -> None:
        prediction = NextActionPredictor().predict(
            snapshot=ActivitySnapshot(
                active_file=ActivityFile(name="app.py", path=r"D:\repo\desktop_assistant\ui\app.py"),
                active_project=ActivityProject(name="desktop_assistant", path=r"D:\repo\desktop_assistant"),
            ),
            todos=[],
        )

        self.assertEqual(prediction.source, "context_completion")
        self.assertEqual(prediction.suggested_text, "继续：desktop_assistant 的 UI 设计")

    def test_prediction_store_round_trips_json(self) -> None:
        root = _workspace_path()
        try:
            store = NextActionPredictionStore(root / "prediction.json")
            prediction = NextActionPredictor().predict(
                snapshot=ActivitySnapshot(active_app=ActivityApp(name="QQ")),
                todos=[],
            )

            store.save(prediction)
            loaded = store.load()

            self.assertEqual(loaded.suggested_text, "查看待办任务清单")
            self.assertEqual(loaded.route_hint, "todo")
            self.assertEqual(loaded.source, "fallback")
        finally:
            rmtree(root, ignore_errors=True)

    def test_prediction_store_quarantines_corrupted_json_and_returns_empty_prediction(self) -> None:
        root = _workspace_path()
        try:
            path = root / "prediction.json"
            path.write_text("{not-json", encoding="utf-8")

            loaded = NextActionPredictionStore(path).load()

            self.assertEqual(loaded.suggested_text, "")
            self.assertFalse(path.exists())
            quarantined = list(root.glob("prediction.json.corrupt*"))
            self.assertEqual(len(quarantined), 1)
        finally:
            rmtree(root, ignore_errors=True)


class _FakeSampler:
    def __init__(self, snapshot: ActivitySnapshot, activity_store: ActivityStore) -> None:
        self.snapshot = snapshot
        self.activity_store = activity_store

    def sample(self) -> ActivitySnapshot:
        return self.snapshot


class ActivityPrivacyTests(unittest.TestCase):
    def test_privacy_can_redact_paths_or_skip_excluded_apps(self) -> None:
        snapshot = ActivitySnapshot(
            active_app=ActivityApp(name="SecretApp"),
            active_file=ActivityFile(name="secret.docx", path=r"D:\secret.docx"),
            recent_files=[ActivityFile(name="a.txt", path=r"D:\a.txt")],
        )

        redacted = apply_activity_privacy(snapshot, ActivityPrivacySettings(save_file_paths=False))
        skipped = apply_activity_privacy(snapshot, ActivityPrivacySettings(excluded_apps=["secret"]))

        self.assertEqual(redacted.active_file.path, "")
        self.assertEqual(redacted.recent_files[0].path, "")
        self.assertIsNone(skipped)

    def test_sampling_service_respects_privacy_and_writes_prediction(self) -> None:
        root = _workspace_path()
        try:
            snapshot = ActivitySnapshot(active_app=ActivityApp(name="Cursor"))
            activity_store = ActivityStore(root / "activity.json")
            privacy_store = ActivityPrivacyStore(root / "privacy.json")
            privacy_store.save(ActivityPrivacySettings(save_file_paths=False))
            tracker = HabitTracker(
                sampler=_FakeSampler(snapshot, activity_store),
                journal=DailyActivityJournal(root / "days"),
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                privacy_store=privacy_store,
            )

            result = ActivitySamplingService(tracker=tracker, privacy_store=privacy_store).tick()

            self.assertTrue(result.captured)
            self.assertEqual(len(activity_store.load()), 1)
            self.assertTrue((root / "prediction.json").exists())
        finally:
            rmtree(root, ignore_errors=True)

    def test_privacy_store_quarantines_corrupted_json_and_returns_defaults(self) -> None:
        root = _workspace_path()
        try:
            path = root / "privacy.json"
            path.write_text("{not-json", encoding="utf-8")

            settings = ActivityPrivacyStore(path).load()

            self.assertTrue(settings.enabled)
            self.assertFalse(path.exists())
            quarantined = list(root.glob("privacy.json.corrupt*"))
            self.assertEqual(len(quarantined), 1)
        finally:
            rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
