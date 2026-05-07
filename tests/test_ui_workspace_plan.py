from __future__ import annotations

import os
import unittest
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from desktop_assistant.habits import NextActionPredictionStore
from desktop_assistant.models import ActionStep, ActionType, RiskLevel
from desktop_assistant.recipe import RecipeStore
from desktop_assistant.todo import TodoStore
from desktop_assistant.ui.shell_controller import AssistantShellController
from desktop_assistant.workspace import WorkspaceDraftStore, WorkspaceService


def _workspace_path() -> Path:
    base = Path.cwd() / "runtime" / "test_ui_workspace_plan"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


class WorkspacePlanEditorTests(unittest.TestCase):
    def test_workspace_plan_editor_controls_confirmed_actions(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            draft_store = WorkspaceDraftStore(root / "drafts.json")
            recipe_store = RecipeStore(root / "recipes.json")
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                workspace_service=WorkspaceService(draft_store=draft_store, recipe_store=recipe_store),
            )
            window.show()
            window._show_workspace_page()
            window.workspace_input.setText("打开 https://example.com")
            window._generate_workspace()
            app.processEvents()

            self.assertEqual(window.workspace_plan_action_list.count(), 1)
            self.assertIn("打开网页", window.workspace_plan_action_list.item(0).text())
            window.workspace_plan_action_list.item(0).setCheckState(Qt.CheckState.Unchecked)
            window.workspace_plan_action_type_combo.setCurrentIndex(
                window.workspace_plan_action_type_combo.findData("open_url")
            )
            window.workspace_plan_action_target_input.setEditText("https://openai.com")
            window._add_workspace_plan_action()
            window.workspace_plan_action_list.setCurrentRow(1)
            window.workspace_plan_action_target_input.setEditText("https://openai.com/docs")
            window._update_workspace_plan_action()
            window.workspace_plan_action_target_input.setEditText("https://remove.example")
            window._add_workspace_plan_action()
            window.workspace_plan_action_list.setCurrentRow(2)
            window._remove_workspace_plan_action()
            window._save_workspace()

            pending = draft_store.latest_pending()
            self.assertIsNotNone(pending)
            self.assertEqual([step.target for step in pending.plan.steps], ["https://openai.com/docs"])

            window._plan_workspace_goal()
            preview = window.workspace_confirm_text.toPlainText()
            self.assertIn("https://openai.com/docs", preview)
            self.assertNotIn("https://example.com", preview)
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_workspace_recipe_can_be_saved_and_loaded_from_picker(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            recipe_store = RecipeStore(root / "recipes.json")
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                workspace_service=WorkspaceService(
                    draft_store=WorkspaceDraftStore(root / "drafts.json"),
                    recipe_store=recipe_store,
                ),
            )
            window.show()
            window._show_workspace_page()
            window.workspace_input.setText("打开 https://example.com")
            window._generate_workspace()
            window._save_workspace()
            app.processEvents()

            recipes = recipe_store.load()
            self.assertEqual(len(recipes), 1)
            self.assertEqual(recipes[0].scenario, "workspace")
            self.assertEqual([step.target for step in recipes[0].plan.steps], ["https://example.com"])
            self.assertEqual(window.workspace_recipe_combo.currentData(), recipes[0].id)

            window.current_suggestion = None
            window.workspace_input.clear()
            window.workspace_plan_action_list.clear()
            window._load_workspace_recipe()

            self.assertEqual(window.workspace_input.text(), "打开 https://example.com")
            self.assertEqual(window.workspace_plan_action_list.count(), 1)
            self.assertIn("https://example.com", window.workspace_plan_action_list.item(0).text())

            window._plan_workspace_goal()
            self.assertIn("https://example.com", window.workspace_confirm_text.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)

    def test_home_goal_matching_saved_recipe_opens_confirmation_directly(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from desktop_assistant.ui.shell_window import AssistantShellWindow

        app = QApplication.instance() or QApplication([])
        root = _workspace_path()
        window = AssistantShellWindow()
        try:
            recipe_store = RecipeStore(root / "recipes.json")
            recipe_store.create_from_steps(
                name="写周报方案",
                user_goal="写周报",
                plan_name="weekly",
                risk_level=RiskLevel.LOW,
                scenario="workspace",
                steps=[ActionStep(action_type=ActionType.OPEN_URL, target="https://example.com/report")],
            )
            window.controller = AssistantShellController(
                todo_store=TodoStore(root / "todos.json"),
                prediction_store=NextActionPredictionStore(root / "prediction.json"),
                workspace_service=WorkspaceService(
                    draft_store=WorkspaceDraftStore(root / "drafts.json"),
                    recipe_store=recipe_store,
                ),
            )
            window.show()
            window._refresh_home()

            window._submit_text("写周报", False)
            app.processEvents()

            self.assertIs(window.stack.currentWidget(), window.workspace_confirm_page)
            self.assertIn("https://example.com/report", window.workspace_confirm_text.toPlainText())
        finally:
            window.close()
            rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
