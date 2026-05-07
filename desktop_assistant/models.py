from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunMode(str, Enum):
    NORMAL = "normal"
    DRY_RUN = "dry_run"
    STEP_BY_STEP = "step_by_step"
    MODULE_TEST = "module_test"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(str, Enum):
    OPEN_APP = "open_app"
    FOCUS_APP = "focus_app"
    LIST_WINDOWS = "list_windows"
    FOCUS_WINDOW = "focus_window"
    MINIMIZE_WINDOW = "minimize_window"
    MAXIMIZE_WINDOW = "maximize_window"
    RESTORE_WINDOW = "restore_window"
    CLOSE_WINDOW = "close_window"
    OPEN_URL = "open_url"
    OPEN_PROJECT = "open_project"
    OPEN_FOLDER = "open_folder"
    OPEN_FILE = "open_file"
    ANSWER_QUERY = "answer_query"
    SHOW_TASKS = "show_tasks"
    RESTORE_WORKSPACE = "restore_workspace"
    CREATE_REMINDER = "create_reminder"
    START_FOCUS_TIMER = "start_focus_timer"


class UserDecision(str, Enum):
    REJECT = "reject"
    RUN_ONCE = "run_once"
    WHITELIST = "whitelist"


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    PENDING = "pending"


class WorkflowStatus(str, Enum):
    PREPARED = "prepared"
    DRY_RUN_READY = "dry_run_ready"
    PARTIAL = "partial"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


class RecoveryContext(BaseModel):
    original_user_request: str
    failed_step_index: int
    failed_action_type: str
    failed_target: str
    failure_status: str
    failure_message: str
    failure_code: str | None = None
    failure_details: dict[str, Any] = Field(default_factory=dict)
    suggested_remedy: str | None = None
    previous_plan_name: str
    failed_attempts_for_action: int = 0
    recovery_attempt: int = 1
    recovery_category: str | None = None
    recovery_strategy: str | None = None
    recovery_guidance: list[str] = Field(default_factory=list)


class PlanRefinementContext(BaseModel):
    original_goal: str
    current_plan: "ActionPlan"
    user_refinement: str
    constraints: list[str] = Field(default_factory=list)
    revision_index: int = 1
    recipe_id: str | None = None


class RecoveryEvent(BaseModel):
    failed_step_index: int
    failed_action_type: str
    failed_target: str
    failure_code: str | None = None
    recovery_status: str
    message: str
    inserted_steps: int = 0


class WorkflowRequest(BaseModel):
    user_request: str
    task_title: str | None = None
    scene_name: str | None = None
    run_mode: RunMode = RunMode.NORMAL
    user_decision: UserDecision = UserDecision.RUN_ONCE
    current_step: int = 0
    recovery_context: RecoveryContext | None = None
    plan_refinement: PlanRefinementContext | None = None


class ContextSnapshot(BaseModel):
    local_time: str
    date_label: str
    weekday: str
    timezone: str
    weather: str | None = None
    holiday: bool = False


class ActionStep(BaseModel):
    action_type: ActionType
    target: str
    params: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    reason: str = ""


class ActionPlan(BaseModel):
    plan_name: str
    source: str
    steps: list[ActionStep] = Field(default_factory=list)


class IntentInterpretation(BaseModel):
    user_goal: str
    primary_intent: str
    target_kind: str
    target_name: str
    confidence: str
    needs_clarification: bool
    clarification_question: str | None = None
    reasoning_summary: str = ""


class AppIntentMatch(BaseModel):
    local_app_request: bool
    action_type: str
    target_name: str
    confidence: str
    needs_clarification: bool
    clarification_question: str | None = None
    reasoning_summary: str = ""


class PlannerResult(BaseModel):
    intent_summary: str
    requires_clarification: bool = False
    action_plan: ActionPlan
    risk_guess: RiskLevel = RiskLevel.LOW
    reasoning_summary: str = ""
    intent_interpretation: IntentInterpretation | None = None
    selected_intent_template: str | None = None
    selected_planner_template: str | None = None


class PolicyIssue(BaseModel):
    code: str
    message: str


class ActionDecision(BaseModel):
    step_index: int
    action_type: ActionType
    target: str
    risk_level: RiskLevel
    requires_confirmation: bool
    whitelisted: bool = False
    reason: str = ""


class PolicyDecision(BaseModel):
    approved: bool
    risk_level: RiskLevel
    requires_user_confirmation: bool
    issues: list[PolicyIssue] = Field(default_factory=list)
    action_decisions: list[ActionDecision] = Field(default_factory=list)


class ReviewResult(BaseModel):
    approved: bool
    risk_level: RiskLevel
    needs_user_confirmation: bool
    review_summary: str
    issues: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None


class ExecutionDiagnosis(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    remedy: str | None = None


class ExecutionStepResult(BaseModel):
    step_index: int
    action: ActionStep
    status: ExecutionStatus
    message: str
    diagnosis: ExecutionDiagnosis | None = None
    elapsed_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowTrace(BaseModel):
    trace_id: str
    request: WorkflowRequest
    context: ContextSnapshot
    planner_result: PlannerResult
    policy_decision: PolicyDecision
    review_result: ReviewResult
    ai_backend: str = "fake"
    provider_config_path: str | None = None
    prepare_error: ExecutionDiagnosis | None = None
    step_results: list[ExecutionStepResult] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PREPARED
    recovery_attempts: int = 0
    recovery_events: list[RecoveryEvent] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)


class DebugRunRecord(BaseModel):
    id: str
    trace_id: str
    run_mode: RunMode
    trigger_source: str
    input_json: dict[str, Any]
    current_step: int = 0
    status: WorkflowStatus
    snapshot_json: dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None


class RecentTraceRecord(BaseModel):
    trace_id: str
    status: WorkflowStatus
    created_at: str
    updated_at: str
    trace: WorkflowTrace
