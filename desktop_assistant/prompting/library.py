from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import ContextSnapshot, IntentInterpretation, WorkflowRequest
from .models import RenderedPrompt
from .rendering import (
    default_template_path,
    fill_template,
    intent_interpretation_summary,
    plan_refinement_summary,
    recovery_context_summary,
)


class PromptTemplateLibrary:
    """Load reusable prompt templates and render request-specific prompts."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_template_path()
        self._payload = json.loads(self.path.read_text(encoding="utf-8"))

    @classmethod
    def default(cls) -> "PromptTemplateLibrary":
        return cls()

    def render_planner_prompt(
        self,
        *,
        request: WorkflowRequest,
        context: ContextSnapshot,
        allowed_actions: list[str],
        app_inventory_summary: str,
        intent_interpretation: IntentInterpretation | None = None,
        capability_summary: str | None = None,
    ) -> RenderedPrompt:
        template = self._select_planner_template(request.user_request, intent_interpretation)
        return RenderedPrompt(
            template_id=template["id"],
            system_prompt=fill_template(
                self._payload["planner"]["base"],
                {
                    "allowed_actions": ", ".join(allowed_actions),
                    "capability_summary": capability_summary or "No capability registry summary was provided.",
                    "app_inventory_summary": app_inventory_summary,
                    "intent_interpretation_summary": intent_interpretation_summary(intent_interpretation),
                    "recovery_context_summary": recovery_context_summary(request),
                    "plan_refinement_summary": plan_refinement_summary(request),
                    "template_id": template["id"],
                    "template_body": template["body"],
                    "user_request": request.user_request,
                    "date_label": context.date_label,
                    "timezone": context.timezone,
                },
            ),
        )

    def render_intent_prompt(
        self,
        *,
        request: WorkflowRequest,
        app_inventory_summary: str,
        capability_summary: str | None = None,
    ) -> RenderedPrompt:
        template = self._select_template("intent", request.user_request)
        return RenderedPrompt(
            template_id=template["id"],
            system_prompt=fill_template(
                self._payload["intent"]["base"],
                {
                    "app_inventory_summary": app_inventory_summary,
                    "capability_summary": capability_summary or "No capability registry summary was provided.",
                    "recovery_context_summary": recovery_context_summary(request),
                    "plan_refinement_summary": plan_refinement_summary(request),
                    "template_id": template["id"],
                    "template_body": template["body"],
                    "user_request": request.user_request,
                },
            ),
        )

    def render_app_match_prompt(
        self,
        *,
        request: WorkflowRequest,
        app_name_index_summary: str,
        candidate_app_summary: str | None = None,
    ) -> RenderedPrompt:
        template = self._select_template("app_match", request.user_request)
        return RenderedPrompt(
            template_id=template["id"],
            system_prompt=fill_template(
                self._payload["app_match"]["base"],
                {
                    "app_name_index_summary": app_name_index_summary,
                    "candidate_app_summary": (
                        candidate_app_summary
                        or "No high-relevance candidate shortlist was provided."
                    ),
                    "template_id": template["id"],
                    "template_body": template["body"],
                    "user_request": request.user_request,
                },
            ),
        )

    def render_reviewer_prompt(self, *, request: WorkflowRequest) -> RenderedPrompt:
        template = self._select_template("reviewer", request.user_request)
        return RenderedPrompt(
            template_id=template["id"],
            system_prompt=fill_template(
                self._payload["reviewer"]["base"],
                {
                    "template_id": template["id"],
                    "template_body": template["body"],
                    "user_request": request.user_request,
                },
            ),
        )

    def _select_template(self, section: str, user_request: str) -> dict[str, Any]:
        lowered = user_request.lower()
        templates = self._payload[section]["templates"]
        default_template = templates[-1]
        for template in templates:
            markers = template.get("markers", [])
            if markers and any(str(marker).lower() in lowered for marker in markers):
                return template
            if not markers:
                default_template = template
        return default_template

    def _select_planner_template(
        self,
        user_request: str,
        intent_interpretation: IntentInterpretation | None,
    ) -> dict[str, Any]:
        if intent_interpretation is not None:
            template_id_by_intent = {
                "open_local_app": "planner.local_app",
                "open_website": "planner.open_web",
                "web_lookup": "planner.web_lookup",
                "window_management": "planner.window_management",
                "workspace_prepare": "planner.workspace",
            }
            template_id = template_id_by_intent.get(intent_interpretation.primary_intent)
            if template_id is not None:
                return self._template_by_id("planner", template_id)
        return self._select_template("planner", user_request)

    def _template_by_id(self, section: str, template_id: str) -> dict[str, Any]:
        for template in self._payload[section]["templates"]:
            if template["id"] == template_id:
                return template
        raise KeyError(f"Unknown prompt template: {section}.{template_id}")
