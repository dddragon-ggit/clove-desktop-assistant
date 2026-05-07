from __future__ import annotations

from typing import Any, Iterable

from ..models import ActionStep, ActionType, PolicyIssue, RiskLevel
from .defaults import _default_capabilities
from .models import CapabilityDefinition
from .validation import max_risk, validate_common, validate_open_app, validate_open_url, validate_path_target


class CapabilityRegistry:
    """Single source of truth for actions the assistant can plan and execute."""

    def __init__(self, capabilities: Iterable[CapabilityDefinition]) -> None:
        self._capabilities = {capability.action_type: capability for capability in capabilities}

    @classmethod
    def default(cls) -> "CapabilityRegistry":
        return cls(_default_capabilities())

    def get(self, action_type: ActionType) -> CapabilityDefinition | None:
        return self._capabilities.get(action_type)

    def all_capabilities(self) -> list[CapabilityDefinition]:
        return list(self._capabilities.values())

    def enabled_capabilities(self) -> list[CapabilityDefinition]:
        return [capability for capability in self._capabilities.values() if capability.execution_mode != "disabled"]

    def allowed_action_values(self) -> list[str]:
        return [capability.action_type.value for capability in self.enabled_capabilities()]

    def to_provider_payload(self) -> list[dict[str, Any]]:
        return [capability.to_provider_payload() for capability in self.enabled_capabilities()]

    def prompt_summary(self) -> str:
        return "\n".join(capability.to_prompt_line() for capability in self.enabled_capabilities())

    def validate_action(self, action: ActionStep) -> list[PolicyIssue]:
        capability = self.get(action.action_type)
        if capability is None:
            return [
                PolicyIssue(
                    code="ACTION_NOT_REGISTERED",
                    message=f"Action {action.action_type.value} is not registered as a capability.",
                )
            ]

        issues = validate_common(action)
        if capability.execution_mode == "disabled":
            issues.append(
                PolicyIssue(
                    code="CAPABILITY_DISABLED",
                    message=f"Capability {action.action_type.value} is registered but not enabled for execution.",
                )
            )
        if action.action_type == ActionType.OPEN_URL:
            issues.extend(validate_open_url(action))
        elif action.action_type in {ActionType.OPEN_APP, ActionType.FOCUS_APP}:
            issues.extend(validate_open_app(action))
        elif action.action_type in {ActionType.OPEN_FOLDER, ActionType.OPEN_FILE, ActionType.OPEN_PROJECT}:
            issues.extend(validate_path_target(action))
        return issues

    def effective_risk(self, action: ActionStep) -> RiskLevel:
        capability = self.get(action.action_type)
        if capability is None:
            return action.risk_level
        return max_risk(action.risk_level, capability.default_risk)
