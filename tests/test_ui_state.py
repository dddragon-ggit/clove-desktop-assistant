from __future__ import annotations

import unittest
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from desktop_assistant.ui_state import AssistantShellMode, AssistantUiStateStore


def _workspace_path() -> Path:
    base = Path.cwd() / "runtime" / "test_ui_state"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


class AssistantUiStateStoreTests(unittest.TestCase):
    def test_ui_state_persists_panel_orb_and_preferences(self) -> None:
        root = _workspace_path()
        try:
            store = AssistantUiStateStore(root / "ui_state.json")
            store.update_panel(x=10, y=20, width=400, height=240)
            store.update_orb(x=30, y=40, hidden=True)
            state = store.update_preferences(opacity=1.5, blur_enabled=False)
            loaded = AssistantUiStateStore(root / "ui_state.json").load()

            self.assertEqual(state.opacity, 1.0)
            self.assertEqual(loaded.mode, AssistantShellMode.ORB)
            self.assertTrue(loaded.orb_hidden)
            self.assertFalse(loaded.blur_enabled)
            self.assertEqual(loaded.panel.width, 400)
        finally:
            rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
