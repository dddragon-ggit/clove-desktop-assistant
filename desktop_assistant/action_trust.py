from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .models import ActionStep, RiskLevel
from .storage import quarantine_corrupted_file, write_json_atomic


ACTION_TRUST_SCHEMA_VERSION = 1


class TrustedActionRule(BaseModel):
    key: str
    action_type: str
    target: str
    params: dict[str, Any] = Field(default_factory=dict)
    risk_level: str
    created_at: str
    note: str = ""


def default_action_trust_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "action_whitelist.json"


class ActionTrustStore:
    """Persist user-approved action-level trust rules."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_action_trust_path()

    def load(self) -> list[TrustedActionRule]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            quarantine_corrupted_file(
                self.path,
                source="action_trust_store",
                category="action_trust_store_corrupted",
                reason="Action trust JSON is unreadable.",
            )
            return []
        if not isinstance(payload, dict):
            quarantine_corrupted_file(
                self.path,
                source="action_trust_store",
                category="action_trust_store_invalid",
                reason="Action trust root must be a JSON object.",
            )
            return []
        raw_rules = payload.get("trusted_actions") or []
        if not isinstance(raw_rules, list):
            quarantine_corrupted_file(
                self.path,
                source="action_trust_store",
                category="action_trust_store_invalid",
                reason="Action trust trusted_actions must be a list.",
            )
            return []
        rules: list[TrustedActionRule] = []
        try:
            for item in raw_rules:
                if not isinstance(item, dict):
                    continue
                rules.append(TrustedActionRule.model_validate(item))
        except Exception:
            quarantine_corrupted_file(
                self.path,
                source="action_trust_store",
                category="action_trust_store_invalid",
                reason="Action trust items could not be validated.",
            )
            return []
        return rules

    def save(self, rules: Iterable[TrustedActionRule]) -> None:
        payload = {
            "schema_version": ACTION_TRUST_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "trusted_actions": [rule.model_dump(mode="json") for rule in rules],
        }
        write_json_atomic(self.path, payload)

    def trusted_keys(self) -> set[str]:
        return {rule.key for rule in self.load()}

    def is_trusted(self, action: ActionStep) -> bool:
        return action_trust_key(action) in self.trusted_keys()

    def trust_action(self, action: ActionStep, risk_level: RiskLevel, *, note: str = "") -> TrustedActionRule:
        rules_by_key = {rule.key: rule for rule in self.load()}
        key = action_trust_key(action)
        rule = TrustedActionRule(
            key=key,
            action_type=action.action_type.value,
            target=action.target,
            params=action.params,
            risk_level=risk_level.value,
            created_at=datetime.now(UTC).isoformat(),
            note=note,
        )
        rules_by_key[key] = rule
        self.save(rules_by_key.values())
        return rule

    def delete(self, key: str) -> bool:
        rules = self.load()
        kept = [rule for rule in rules if rule.key != key]
        if len(kept) == len(rules):
            return False
        self.save(kept)
        return True


def action_trust_key(action: ActionStep) -> str:
    payload = {
        "action_type": action.action_type.value,
        "target": action.target.strip(),
        "params": _stable_json(action.params),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_json(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
