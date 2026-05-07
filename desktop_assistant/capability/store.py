from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from ..models import ActionType
from ..storage import quarantine_corrupted_file, write_json_atomic
from .models import CapabilityDefinition
from .registry import CapabilityRegistry


CAPABILITY_CATALOG_SCHEMA_VERSION = 1


def default_capability_catalog_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "capabilities.json"


class CapabilityStore:
    """Persist the capability catalog so tools can be inspected and tuned outside code."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_capability_catalog_path()

    def ensure(
        self,
        *,
        refresh: bool = False,
        available_handler_names: Iterable[str] | None = None,
    ) -> CapabilityRegistry:
        if self.path.exists() and not refresh:
            try:
                registry = self.load(available_handler_names=available_handler_names)
                self.save(registry)
                return registry
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, OSError):
                pass

        registry = CapabilityRegistry.default()
        self.save(registry)
        return _apply_handler_availability(registry, available_handler_names)

    def load(self, *, available_handler_names: Iterable[str] | None = None) -> CapabilityRegistry:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as exc:
            quarantine_corrupted_file(
                self.path,
                source="capability_store",
                category="capability_catalog_corrupted",
                reason="Capability catalog JSON is unreadable.",
            )
            raise ValueError(f"Capability catalog is unreadable: {self.path}") from exc
        if not isinstance(payload, dict):
            quarantine_corrupted_file(
                self.path,
                source="capability_store",
                category="capability_catalog_invalid",
                reason="Capability catalog root must be a JSON object.",
            )
            raise ValueError("Capability catalog must be a JSON object.")
        registry = _registry_from_payload(payload)
        return _apply_handler_availability(registry, available_handler_names)

    def save(self, registry: CapabilityRegistry) -> None:
        payload = {
            "schema_version": CAPABILITY_CATALOG_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "capabilities": [capability.to_json() for capability in registry.all_capabilities()],
        }
        write_json_atomic(self.path, payload)

    def update_capability(
        self,
        action_type: ActionType,
        *,
        execution_mode: str | None = None,
        default_risk: str | None = None,
        handler_name: str | None = None,
        description: str | None = None,
        available_handler_names: Iterable[str] | None = None,
    ) -> CapabilityRegistry:
        registry = self.ensure(available_handler_names=None)
        capabilities = []
        for capability in registry.all_capabilities():
            if capability.action_type != action_type:
                capabilities.append(capability)
                continue
            payload = capability.to_json()
            if execution_mode is not None:
                payload["execution_mode"] = execution_mode
            if default_risk is not None:
                payload["default_risk"] = default_risk
            if handler_name is not None:
                payload["handler_name"] = handler_name
            if description is not None:
                payload["description"] = description
            capabilities.append(CapabilityDefinition.from_json(payload))
        updated = CapabilityRegistry(capabilities)
        self.save(updated)
        return _apply_handler_availability(updated, available_handler_names)


def _registry_from_payload(payload: dict[str, Any]) -> CapabilityRegistry:
    defaults = {capability.action_type: capability for capability in CapabilityRegistry.default().all_capabilities()}
    raw_capabilities = payload.get("capabilities") or []
    if not isinstance(raw_capabilities, list):
        raise ValueError("Capability catalog capabilities must be a list.")

    for item in raw_capabilities:
        if not isinstance(item, dict):
            continue
        try:
            action_type = ActionType(str(item.get("action_type")))
        except ValueError:
            continue
        base = defaults.get(action_type)
        if base is None:
            continue
        defaults[action_type] = _merge_capability_payload(base, item)
    return CapabilityRegistry(defaults.values())


def _merge_capability_payload(base: CapabilityDefinition, override: dict[str, Any]) -> CapabilityDefinition:
    payload = base.to_json()
    for key in [
        "title",
        "description",
        "target_schema",
        "params_schema",
        "default_risk",
        "execution_mode",
        "handler_name",
        "safety_rules",
        "planner_guidance",
    ]:
        if key in override:
            if _is_legacy_simulated_todo_capability(base, key, override):
                continue
            payload[key] = override[key]
    return CapabilityDefinition.from_json(payload)


def _is_legacy_simulated_todo_capability(
    base: CapabilityDefinition,
    key: str,
    override: dict[str, Any],
) -> bool:
    if base.action_type.value not in {"show_tasks", "create_reminder"}:
        return False
    if key not in {"execution_mode", "handler_name"}:
        return False
    return (
        str(override.get("execution_mode") or "") == "simulated"
        or str(override.get("handler_name") or "") == "simulated"
    )


def _apply_handler_availability(
    registry: CapabilityRegistry,
    available_handler_names: Iterable[str] | None,
) -> CapabilityRegistry:
    if available_handler_names is None:
        return registry

    available = set(available_handler_names)
    capabilities: list[CapabilityDefinition] = []
    for capability in registry.all_capabilities():
        if capability.execution_mode == "real" and capability.handler_name not in available:
            capabilities.append(
                capability.with_execution_mode(
                    "disabled",
                    safety_rule=f"Handler {capability.handler_name or '(none)'} is unavailable.",
                )
            )
        else:
            capabilities.append(capability)
    return CapabilityRegistry(capabilities)
