from __future__ import annotations

from typing import Protocol

from .models import (
    ActionStep,
    ContextSnapshot,
    DebugRunRecord,
    ExecutionStepResult,
    PlannerResult,
    PolicyDecision,
    RecentTraceRecord,
    ReviewResult,
    WorkflowRequest,
    WorkflowTrace,
)


class PlannerProtocol(Protocol):
    def plan(self, request: WorkflowRequest, context: ContextSnapshot) -> PlannerResult:
        """Return a structured action plan for a request."""


class ReviewerProtocol(Protocol):
    def review(
        self,
        request: WorkflowRequest,
        planner_result: PlannerResult,
        policy_decision: PolicyDecision,
        context: ContextSnapshot,
    ) -> ReviewResult:
        """Review a structured plan before execution."""


class ExecutorProtocol(Protocol):
    def execute(self, action: ActionStep, step_index: int, trace_id: str) -> ExecutionStepResult:
        """Execute or simulate a single action step."""


class ContextProviderProtocol(Protocol):
    def get_context(self) -> ContextSnapshot:
        """Return current context information."""


class StorageProtocol(Protocol):
    def save_trace(self, trace: WorkflowTrace) -> None:
        """Persist a workflow trace."""

    def get_trace(self, trace_id: str) -> WorkflowTrace:
        """Load a workflow trace."""

    def save_debug_run(self, debug_run: DebugRunRecord) -> None:
        """Persist a debug run snapshot."""

    def list_debug_runs(self, trace_id: str | None = None) -> list[DebugRunRecord]:
        """Return debug snapshots for a trace or all traces."""

    def list_recent_traces(self, limit: int = 10) -> list[RecentTraceRecord]:
        """Return recent workflow traces, newest first."""
