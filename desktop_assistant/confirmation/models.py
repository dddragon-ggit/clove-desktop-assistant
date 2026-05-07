from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ConfirmationChoice(str, Enum):
    REJECT = "reject"
    RUN_ONCE = "run_once"
    TRUST_ALWAYS = "trust_always"


class ActionConfirmationCard(BaseModel):
    step_index: int
    action_type: str
    target: str
    risk_level: str
    requires_confirmation: bool
    whitelisted: bool = False
    reason: str = ""
    trust_key: str


class ConfirmationFlow(BaseModel):
    approved_by_policy: bool
    requires_user_confirmation: bool
    choices: list[ConfirmationChoice] = Field(default_factory=list)
    action_cards: list[ActionConfirmationCard] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class ConfirmationApplyResult(BaseModel):
    choice: ConfirmationChoice
    accepted: bool
    trusted_keys: list[str] = Field(default_factory=list)
    message: str = ""
