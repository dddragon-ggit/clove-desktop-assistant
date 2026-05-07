from __future__ import annotations

from .execution_models import ExecutionCase
from .quality_models import QualityExpectation


DEFAULT_EXECUTION_CASES = [
    ExecutionCase(
        case_id="open_qq_app",
        request="打开 QQ 应用",
        category="local_app",
        quality_expectation=QualityExpectation(
            expected_action_prefix=("open_app",),
            forbidden_action_types=("open_url", "answer_query", "show_tasks", "create_reminder"),
            max_steps=1,
            require_policy_approved=True,
            require_review_approved=True,
            require_planner_clarification=False,
        ),
        verification_action_types=("open_app",),
        notes="Launch or focus QQ, then verify a visible app window when possible.",
    ),
    ExecutionCase(
        case_id="open_cursor_app",
        request="打开 Cursor 应用",
        category="local_app",
        quality_expectation=QualityExpectation(
            expected_action_prefix=("open_app",),
            forbidden_action_types=("open_url", "answer_query", "show_tasks", "create_reminder"),
            max_steps=1,
            require_policy_approved=True,
            require_review_approved=True,
            require_planner_clarification=False,
        ),
        verification_action_types=("open_app",),
        notes="Launch or focus Cursor, then verify a visible app window when possible.",
    ),
    ExecutionCase(
        case_id="open_wechat_app",
        request="打开微信应用",
        category="local_app",
        quality_expectation=QualityExpectation(
            expected_action_prefix=("open_app",),
            forbidden_action_types=("open_url", "answer_query", "show_tasks", "create_reminder"),
            max_steps=1,
            require_policy_approved=True,
            require_review_approved=True,
            require_planner_clarification=False,
        ),
        verification_action_types=("open_app",),
    ),
    ExecutionCase(
        case_id="open_battlenet_app",
        request="打开战网应用",
        category="local_app",
        quality_expectation=QualityExpectation(
            expected_action_prefix=("open_app",),
            forbidden_action_types=("open_url", "answer_query", "show_tasks", "create_reminder"),
            max_steps=1,
            require_policy_approved=True,
            require_review_approved=True,
            require_planner_clarification=False,
        ),
        verification_action_types=("open_app",),
    ),
    ExecutionCase(
        case_id="focus_cursor",
        request="切换到 Cursor",
        category="window_state",
        quality_expectation=QualityExpectation(
            expected_action_prefix=("focus_app",),
            forbidden_action_types=("open_url", "answer_query", "show_tasks", "create_reminder"),
            max_steps=1,
            require_policy_approved=True,
            require_review_approved=True,
            require_planner_clarification=False,
        ),
        verification_action_types=("focus_app",),
        notes="This requires Cursor to already have a visible window.",
    ),
    ExecutionCase(
        case_id="open_current_project",
        request="打开当前项目文件夹",
        category="project_location",
        quality_expectation=QualityExpectation(
            expected_action_prefix=("open_project",),
            forbidden_action_types=("open_url", "answer_query", "show_tasks", "create_reminder"),
            max_steps=1,
            require_policy_approved=True,
            require_review_approved=True,
            require_planner_clarification=False,
        ),
        verification_action_types=(),
        notes="Folder opening is treated as execution success; no window-title verification is required.",
    ),
    ExecutionCase(
        case_id="open_zhihu_site",
        request="打开知乎网页",
        category="browser",
        quality_expectation=QualityExpectation(
            expected_action_prefix=("open_url",),
            forbidden_action_types=("open_app", "answer_query", "show_tasks", "create_reminder"),
            required_target_fragments=("zhihu",),
            max_steps=1,
            require_policy_approved=True,
            require_review_approved=True,
            require_planner_clarification=False,
        ),
        verification_action_types=(),
        notes="Browser open is treated as execution success when the OS accepts the URL.",
    ),
    ExecutionCase(
        case_id="weather_xian_today",
        request="查询今天西安天气",
        category="information_lookup",
        quality_expectation=QualityExpectation(
            expected_action_prefix=("answer_query",),
            forbidden_action_types=("open_url", "show_tasks", "create_reminder"),
            required_target_fragments=("西安", "天气"),
            max_steps=1,
            require_policy_approved=True,
            require_review_approved=True,
            require_planner_clarification=False,
        ),
        verification_action_types=(),
        notes="Executes the read-only web-backed answer_query handler.",
    ),
    ExecutionCase(
        case_id="gold_price_today",
        request="查询今天黄金价格",
        category="information_lookup",
        quality_expectation=QualityExpectation(
            expected_action_prefix=("answer_query",),
            forbidden_action_types=("open_url", "show_tasks", "create_reminder"),
            required_target_fragments=("黄金", "价格"),
            max_steps=1,
            require_policy_approved=True,
            require_review_approved=True,
            require_planner_clarification=False,
        ),
        verification_action_types=(),
        notes="Executes the read-only web-backed answer_query handler.",
    ),
]


def selected_execution_cases(case_ids: list[str] | None, ad_hoc_requests: list[str]) -> list[ExecutionCase]:
    cases = DEFAULT_EXECUTION_CASES
    if case_ids:
        selected = set(case_ids)
        cases = [case for case in DEFAULT_EXECUTION_CASES if case.case_id in selected]

    custom_cases = [
        ExecutionCase(
            case_id=f"custom_{index + 1}",
            request=request,
            category="custom",
            quality_expectation=QualityExpectation(allowed_workflow_statuses=("dry_run_ready", "rejected")),
            verification_action_types=(),
            allow_execution=False,
            notes="Ad hoc requests are planning-only in execution eval.",
        )
        for index, request in enumerate(ad_hoc_requests)
    ]
    return [*cases, *custom_cases]
