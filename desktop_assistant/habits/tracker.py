from __future__ import annotations

from ..activity import ActivityPrivacyStore, ActivitySnapshot, DesktopActivitySampler, apply_activity_privacy
from ..todo import TodoStore
from .journal import DailyActivityJournal
from .models import NextActionPrediction
from .prediction import NextActionPredictionStore, NextActionPredictor
from ..workspace import WorkspaceDraftStore


class HabitTracker:
    """Capture activity once and refresh journal + next-action prediction."""

    def __init__(
        self,
        *,
        sampler: DesktopActivitySampler | None = None,
        journal: DailyActivityJournal | None = None,
        todo_store: TodoStore | None = None,
        prediction_store: NextActionPredictionStore | None = None,
        predictor: NextActionPredictor | None = None,
        privacy_store: ActivityPrivacyStore | None = None,
        workspace_draft_store: WorkspaceDraftStore | None = None,
    ) -> None:
        self.sampler = sampler or DesktopActivitySampler()
        self.journal = journal or DailyActivityJournal()
        self.todo_store = todo_store or TodoStore()
        self.prediction_store = prediction_store or NextActionPredictionStore()
        self.predictor = predictor or NextActionPredictor()
        self.privacy_store = privacy_store or ActivityPrivacyStore()
        self.workspace_draft_store = workspace_draft_store or WorkspaceDraftStore()

    def capture_once(self) -> tuple[ActivitySnapshot | None, NextActionPrediction]:
        raw_snapshot = self.sampler.sample()
        snapshot = apply_activity_privacy(raw_snapshot, self.privacy_store.load())
        if snapshot is None:
            prediction = self.predictor.predict(
                todos=self.todo_store.list(include_done=False),
                activity_history=self.sampler.activity_store.recent(limit=50),
                pending_workspace=self.workspace_draft_store.latest_pending(),
            )
            self.prediction_store.save(prediction)
            return None, prediction
        self.sampler.activity_store.append(snapshot)
        self.journal.append_snapshot(snapshot)
        self.journal.prune_old(keep_days=14)
        prediction = self.predictor.predict(
            snapshot=snapshot,
            todos=self.todo_store.list(include_done=False),
            activity_history=self.sampler.activity_store.recent(limit=50),
            pending_workspace=self.workspace_draft_store.latest_pending(),
        )
        self.prediction_store.save(prediction)
        return snapshot, prediction
