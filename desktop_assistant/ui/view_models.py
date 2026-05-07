from __future__ import annotations

from pydantic import BaseModel, Field


class ActionStepSummary(BaseModel):
    order: int
    action_type: str
    target: str
    risk_level: str
    reason: str
    requires_confirmation: bool = False
    whitelisted: bool = False
    execution_status: str | None = None
    execution_message: str | None = None
    failure_code: str | None = None
    failure_remedy: str | None = None
    failure_details: dict = Field(default_factory=dict)
    elapsed_seconds: float | None = None
    metadata: dict = Field(default_factory=dict)


class WorkflowSummary(BaseModel):
    trace_id: str
    status: str
    intent_summary: str
    plan_name: str
    plan_source: str
    selected_intent_template: str | None = None
    selected_planner_template: str | None = None
    planner_risk: str
    timings: dict[str, float] = Field(default_factory=dict)
    policy_approved: bool
    policy_risk: str
    policy_requires_confirmation: bool
    policy_issues: list[str] = Field(default_factory=list)
    review_approved: bool
    review_risk: str
    review_needs_confirmation: bool
    review_summary: str
    review_issues: list[str] = Field(default_factory=list)
    requires_confirmation: bool
    can_run_once: bool
    decision_state: str
    prepare_error_code: str | None = None
    prepare_error_message: str | None = None
    prepare_error_stage: str | None = None
    prepare_error_remedy: str | None = None
    recovery_notice: str | None = None
    steps: list[ActionStepSummary] = Field(default_factory=list)


class RecentTraceSummary(BaseModel):
    trace_id: str
    updated_at: str
    request: str
    status: str
    risk_level: str


class DebugRunSummary(BaseModel):
    id: str
    trace_id: str
    run_mode: str
    status: str
    current_step: int
    created_at: str
    updated_at: str
    snapshot_text: str


class RecoveryEventSummary(BaseModel):
    id: str
    created_at: str
    source: str
    category: str
    path: str
    quarantined_path: str
    reason: str = ""


class CapabilitySummary(BaseModel):
    action_type: str
    title: str
    description: str
    execution_mode: str
    handler_name: str
    handler_status: str = "not_checked"
    handler_available: bool = False
    default_risk: str
    enabled: bool
    target_schema: dict = Field(default_factory=dict)
    params_schema: dict = Field(default_factory=dict)
    safety_rules: list[str] = Field(default_factory=list)
    planner_guidance: list[str] = Field(default_factory=list)
    catalog_path: str = ""
    recent_failure_count: int = 0
    recent_failure_code: str | None = None
    recent_failure_message: str | None = None
    recent_failure_remedy: str | None = None
    recent_failure_trace_id: str | None = None
    recent_failure_updated_at: str | None = None
    health_label: str = ""
    risk_explanation: str = ""
    test_hint: str = ""


class WindowStateSummary(BaseModel):
    hwnd: int
    title: str = ""
    process_id: int = 0
    executable_path: str = ""
    is_minimized: bool = False
    is_maximized: bool = False
    is_foreground: bool = False
