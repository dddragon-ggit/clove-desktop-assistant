from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..storage import quarantine_corrupted_file, write_json_atomic
from .models import UI_STATE_SCHEMA_VERSION, AssistantShellMode, AssistantUiState, PointState, RectState


def default_ui_state_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "assistant_ui_state.json"


class AssistantUiStateStore:
    """Persist shell-level UI state without depending on PySide widgets."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_ui_state_path()

    def load(self) -> AssistantUiState:
        if not self.path.exists():
            return AssistantUiState()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            quarantine_corrupted_file(self.path, source="ui_state_store", category="ui_state_corrupted", reason="UI state JSON is unreadable.")
            return AssistantUiState()
        state = payload.get("state") if isinstance(payload, dict) else payload
        if not isinstance(state, dict):
            quarantine_corrupted_file(self.path, source="ui_state_store", category="ui_state_invalid", reason="UI state payload is invalid.")
            return AssistantUiState()
        try:
            return AssistantUiState.model_validate(state)
        except Exception:
            quarantine_corrupted_file(self.path, source="ui_state_store", category="ui_state_invalid", reason="UI state could not be validated.")
            return AssistantUiState()

    def save(self, state: AssistantUiState) -> AssistantUiState:
        state.updated_at = datetime.now(UTC).isoformat()
        payload = {
            "schema_version": UI_STATE_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "state": state.model_dump(mode="json"),
        }
        write_json_atomic(self.path, payload)
        return state

    def update_panel(self, *, x: int, y: int, width: int, height: int) -> AssistantUiState:
        state = self.load()
        state.mode = AssistantShellMode.PANEL
        state.panel = RectState(x=x, y=y, width=max(180, width), height=max(140, height))
        return self.save(state)

    def update_orb(self, *, x: int, y: int, hidden: bool | None = None) -> AssistantUiState:
        state = self.load()
        state.mode = AssistantShellMode.ORB
        state.orb = PointState(x=x, y=y)
        if hidden is not None:
            state.orb_hidden = hidden
        return self.save(state)

    def update_preferences(
        self,
        *,
        opacity: float | None = None,
        blur_enabled: bool | None = None,
    ) -> AssistantUiState:
        state = self.load()
        if opacity is not None:
            state.opacity = max(0.1, min(1.0, float(opacity)))
        if blur_enabled is not None:
            state.blur_enabled = blur_enabled
        return self.save(state)
