from __future__ import annotations

from datetime import UTC, datetime

from ..models import DebugRunRecord, RecentTraceRecord, WorkflowTrace


class InMemoryStorage:
    """Simple storage used for local development and testing."""

    def __init__(self) -> None:
        self.traces: dict[str, WorkflowTrace] = {}
        self.debug_runs: dict[str, DebugRunRecord] = {}
        self.trace_timestamps: dict[str, str] = {}

    def save_trace(self, trace: WorkflowTrace) -> None:
        self.traces[trace.trace_id] = trace.model_copy(deep=True)
        self.trace_timestamps[trace.trace_id] = datetime.now(UTC).isoformat()

    def get_trace(self, trace_id: str) -> WorkflowTrace:
        if trace_id not in self.traces:
            raise KeyError(f"Unknown trace_id: {trace_id}")
        return self.traces[trace_id].model_copy(deep=True)

    def save_debug_run(self, debug_run: DebugRunRecord) -> None:
        timestamp = datetime.now(UTC).isoformat()
        stored = debug_run.model_copy(deep=True)
        stored.created_at = stored.created_at or timestamp
        stored.updated_at = timestamp
        self.debug_runs[debug_run.id] = stored

    def list_debug_runs(self, trace_id: str | None = None) -> list[DebugRunRecord]:
        debug_runs = list(self.debug_runs.values())
        if trace_id is not None:
            debug_runs = [debug_run for debug_run in debug_runs if debug_run.trace_id == trace_id]
        return sorted(debug_runs, key=lambda debug_run: debug_run.created_at or "")

    def list_recent_traces(self, limit: int = 10) -> list[RecentTraceRecord]:
        safe_limit = max(1, min(limit, 100))
        trace_ids = sorted(
            self.traces,
            key=lambda trace_id: self.trace_timestamps.get(trace_id, ""),
            reverse=True,
        )
        return [
            RecentTraceRecord(
                trace_id=trace_id,
                status=self.traces[trace_id].status,
                created_at=self.trace_timestamps.get(trace_id, ""),
                updated_at=self.trace_timestamps.get(trace_id, ""),
                trace=self.traces[trace_id].model_copy(deep=True),
            )
            for trace_id in trace_ids[:safe_limit]
        ]
