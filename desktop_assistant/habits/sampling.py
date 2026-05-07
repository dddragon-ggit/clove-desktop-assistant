from __future__ import annotations

import threading
from dataclasses import dataclass

from ..activity import ActivityPrivacyStore, ActivitySnapshot, apply_activity_privacy
from .models import NextActionPrediction
from .tracker import HabitTracker


@dataclass(frozen=True)
class SamplingTickResult:
    captured: bool
    snapshot: ActivitySnapshot | None
    prediction: NextActionPrediction
    message: str = ""


class ActivitySamplingService:
    """Small background loop for runtime activity capture."""

    def __init__(
        self,
        *,
        tracker: HabitTracker | None = None,
        privacy_store: ActivityPrivacyStore | None = None,
        interval_seconds: float = 60.0,
    ) -> None:
        self.tracker = tracker or HabitTracker()
        self.privacy_store = privacy_store or ActivityPrivacyStore()
        self.interval_seconds = max(5.0, float(interval_seconds))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> SamplingTickResult:
        settings = self.privacy_store.load()
        if not settings.enabled:
            prediction = self.tracker.predictor.predict(
                todos=self.tracker.todo_store.list(include_done=False),
                activity_history=self.tracker.sampler.activity_store.recent(limit=50),
                pending_workspace=self.tracker.workspace_draft_store.latest_pending(),
            )
            self.tracker.prediction_store.save(prediction)
            return SamplingTickResult(False, None, prediction, "Activity capture is paused.")
        raw_snapshot = self.tracker.sampler.sample()
        snapshot = apply_activity_privacy(raw_snapshot, settings)
        if snapshot is None:
            prediction = self.tracker.predictor.predict(
                todos=self.tracker.todo_store.list(include_done=False),
                activity_history=self.tracker.sampler.activity_store.recent(limit=50),
                pending_workspace=self.tracker.workspace_draft_store.latest_pending(),
            )
            self.tracker.prediction_store.save(prediction)
            return SamplingTickResult(False, None, prediction, "Activity capture was skipped by privacy settings.")
        self.tracker.sampler.activity_store.append(snapshot)
        self.tracker.journal.append_snapshot(snapshot)
        self.tracker.journal.prune_old(keep_days=14)
        prediction = self.tracker.predictor.predict(
            snapshot=snapshot,
            todos=self.tracker.todo_store.list(include_done=False),
            activity_history=self.tracker.sampler.activity_store.recent(limit=50),
            pending_workspace=self.tracker.workspace_draft_store.latest_pending(),
        )
        self.tracker.prediction_store.save(prediction)
        return SamplingTickResult(True, snapshot, prediction, "Activity captured.")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self, *, timeout_seconds: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout_seconds)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.tick()
            self._stop_event.wait(self.interval_seconds)
