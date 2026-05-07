from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ..models import ActionType, RiskLevel


@dataclass(frozen=True)
class CapabilityDefinition:
    """A registered desktop-assistant capability exposed to planner, policy, and executor."""

    action_type: ActionType
    title: str
    description: str
    target_schema: dict[str, Any]
    params_schema: dict[str, Any]
    default_risk: RiskLevel
    execution_mode: str
    handler_name: str = ""
    safety_rules: tuple[str, ...] = ()
    planner_guidance: tuple[str, ...] = ()

    def to_provider_payload(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "title": self.title,
            "description": self.description,
            "target_schema": self.target_schema,
            "params_schema": self.params_schema,
            "default_risk": self.default_risk.value,
            "execution_mode": self.execution_mode,
            "safety_rules": list(self.safety_rules),
            "planner_guidance": list(self.planner_guidance),
        }

    def to_json(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "title": self.title,
            "description": self.description,
            "target_schema": self.target_schema,
            "params_schema": self.params_schema,
            "default_risk": self.default_risk.value,
            "execution_mode": self.execution_mode,
            "handler_name": self.handler_name,
            "safety_rules": list(self.safety_rules),
            "planner_guidance": list(self.planner_guidance),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "CapabilityDefinition":
        return cls(
            action_type=ActionType(str(payload["action_type"])),
            title=str(payload.get("title") or ""),
            description=str(payload.get("description") or ""),
            target_schema=dict(payload.get("target_schema") or {}),
            params_schema=dict(payload.get("params_schema") or {}),
            default_risk=RiskLevel(str(payload.get("default_risk") or RiskLevel.LOW.value)),
            execution_mode=str(payload.get("execution_mode") or "disabled"),
            handler_name=str(payload.get("handler_name") or ""),
            safety_rules=tuple(str(item) for item in payload.get("safety_rules") or ()),
            planner_guidance=tuple(str(item) for item in payload.get("planner_guidance") or ()),
        )

    def with_execution_mode(self, execution_mode: str, safety_rule: str | None = None) -> "CapabilityDefinition":
        safety_rules = self.safety_rules
        if safety_rule and safety_rule not in safety_rules:
            safety_rules = (*safety_rules, safety_rule)
        return replace(self, execution_mode=execution_mode, safety_rules=safety_rules)

    def to_prompt_line(self) -> str:
        guidance = " ".join(self.planner_guidance)
        rules = " ".join(self.safety_rules)
        return (
            f"- {self.action_type.value}: {self.description} "
            f"target={self.target_schema.get('description', 'string')}; "
            f"params={self.params_schema}; default_risk={self.default_risk.value}; "
            f"mode={self.execution_mode}. {guidance} {rules}"
        ).strip()
