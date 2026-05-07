from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..capabilities import DEFAULT_CAPABILITY_REGISTRY


ACTION_TYPE_VALUES = DEFAULT_CAPABILITY_REGISTRY.allowed_action_values()

RISK_LEVEL_VALUES = ["low", "medium", "high", "critical"]

PRIMARY_INTENT_VALUES = [
    "open_local_app",
    "open_website",
    "web_lookup",
    "open_file_or_folder",
    "window_management",
    "workspace_prepare",
    "task_management",
    "unknown",
]

TARGET_KIND_VALUES = [
    "local_app",
    "website",
    "query",
    "file_path",
    "folder_path",
    "workspace",
    "task",
    "none",
]

CONFIDENCE_VALUES = ["low", "medium", "high"]

APP_INTENT_ACTION_VALUES = ["open_app", "focus_app", "none"]


INTENT_INTERPRETATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "user_goal": {"type": "string"},
        "primary_intent": {"type": "string", "enum": PRIMARY_INTENT_VALUES},
        "target_kind": {"type": "string", "enum": TARGET_KIND_VALUES},
        "target_name": {"type": "string"},
        "confidence": {"type": "string", "enum": CONFIDENCE_VALUES},
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": ["string", "null"]},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "user_goal",
        "primary_intent",
        "target_kind",
        "target_name",
        "confidence",
        "needs_clarification",
        "clarification_question",
        "reasoning_summary",
    ],
}

APP_INTENT_MATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "local_app_request": {"type": "boolean"},
        "action_type": {"type": "string", "enum": APP_INTENT_ACTION_VALUES},
        "target_name": {"type": "string"},
        "confidence": {"type": "string", "enum": CONFIDENCE_VALUES},
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": ["string", "null"]},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "local_app_request",
        "action_type",
        "target_name",
        "confidence",
        "needs_clarification",
        "clarification_question",
        "reasoning_summary",
    ],
}


PLANNER_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent_summary": {"type": "string"},
        "requires_clarification": {"type": "boolean"},
        "action_plan": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "plan_name": {"type": "string"},
                "source": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "action_type": {"type": "string", "enum": ACTION_TYPE_VALUES},
                            "target": {"type": "string"},
                            "risk_level": {"type": "string", "enum": RISK_LEVEL_VALUES},
                            "reason": {"type": "string"},
                        },
                        "required": ["action_type", "target", "risk_level", "reason"],
                    },
                },
            },
            "required": ["plan_name", "source", "steps"],
        },
        "risk_guess": {"type": "string", "enum": RISK_LEVEL_VALUES},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "intent_summary",
        "requires_clarification",
        "action_plan",
        "risk_guess",
        "reasoning_summary",
    ],
}

REVIEW_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "approved": {"type": "boolean"},
        "risk_level": {"type": "string", "enum": RISK_LEVEL_VALUES},
        "needs_user_confirmation": {"type": "boolean"},
        "review_summary": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "rejection_reason": {"type": ["string", "null"]},
    },
    "required": [
        "approved",
        "risk_level",
        "needs_user_confirmation",
        "review_summary",
        "issues",
        "rejection_reason",
    ],
}


def planner_result_schema() -> dict[str, Any]:
    """Return a strict structured-output schema accepted by Responses providers."""

    return deepcopy(PLANNER_RESULT_SCHEMA)


def intent_interpretation_schema() -> dict[str, Any]:
    """Return a strict schema for the API intent-understanding step."""

    return deepcopy(INTENT_INTERPRETATION_SCHEMA)


def app_intent_match_schema() -> dict[str, Any]:
    """Return a strict schema for the lightweight app-intent matching step."""

    return deepcopy(APP_INTENT_MATCH_SCHEMA)


def review_result_schema() -> dict[str, Any]:
    """Return a strict structured-output schema accepted by Responses providers."""

    return deepcopy(REVIEW_RESULT_SCHEMA)
