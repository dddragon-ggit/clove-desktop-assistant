from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from desktop_assistant.adapters.fake import FakeContextProvider
from desktop_assistant.capabilities import CapabilityRegistry
from desktop_assistant.models import ActionPlan, ActionStep, ActionType, RiskLevel, WorkflowRequest
from desktop_assistant.recipes import (
    RecipePlanner,
    RecipeStore,
    WorkflowRecipe,
    build_plan_refinement_context,
    check_recipe,
)
from desktop_assistant.ui.display_text import recipe_detail_text, recipe_label


class RecipeStoreTests(unittest.TestCase):
    def _path(self) -> Path:
        base = Path.cwd() / "runtime" / "test_recipes"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{uuid4().hex}.json"

    def test_create_from_steps_persists_recipe(self) -> None:
        path = self._path()
        store = RecipeStore(path)
        try:
            recipe = store.create_from_steps(
                name="Writing mode",
                user_goal="Start writing",
                plan_name="writing",
                risk_level=RiskLevel.LOW,
                steps=[
                    ActionStep(
                        action_type=ActionType.OPEN_APP,
                        target="Obsidian",
                        risk_level=RiskLevel.LOW,
                        reason="Open notes.",
                    )
                ],
            )
            loaded = RecipeStore(path).find("writing")
        finally:
            if path.exists():
                path.unlink()

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, recipe.id)
        self.assertEqual(loaded.plan.steps[0].target, "Obsidian")
        self.assertEqual(len(loaded.revision_history), 1)
        self.assertEqual(loaded.revision_history[0].note, "Saved plan")

    def test_upsert_existing_recipe_id_updates_recipe(self) -> None:
        path = self._path()
        store = RecipeStore(path)
        try:
            recipe = store.create_from_steps(
                name="Writing mode",
                user_goal="Start writing",
                plan_name="writing",
                risk_level=RiskLevel.LOW,
                steps=[
                    ActionStep(
                        action_type=ActionType.OPEN_APP,
                        target="Obsidian",
                        risk_level=RiskLevel.LOW,
                    )
                ],
            )
            updated = store.create_from_steps(
                recipe_id=recipe.id,
                name="Coding mode",
                user_goal="Start coding",
                plan_name="coding",
                risk_level=RiskLevel.LOW,
                steps=[
                    ActionStep(
                        action_type=ActionType.OPEN_APP,
                        target="Cursor",
                        risk_level=RiskLevel.LOW,
                    )
                ],
            )
            loaded = store.get(recipe.id)
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(updated.id, recipe.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "Coding mode")
        self.assertEqual(loaded.plan.steps[0].target, "Cursor")

    def test_delete_removes_recipe(self) -> None:
        path = self._path()
        store = RecipeStore(path)
        try:
            recipe = store.create_from_steps(
                name="Writing mode",
                user_goal="Start writing",
                plan_name="writing",
                risk_level=RiskLevel.LOW,
                steps=[],
            )
            deleted = store.delete(recipe.id)
            missing = store.get(recipe.id)
        finally:
            if path.exists():
                path.unlink()

        self.assertTrue(deleted)
        self.assertIsNone(missing)

    def test_recipe_planner_replays_saved_plan(self) -> None:
        path = self._path()
        store = RecipeStore(path)
        try:
            recipe = store.create_from_steps(
                name="Writing mode",
                user_goal="Start writing",
                plan_name="writing",
                risk_level=RiskLevel.LOW,
                steps=[
                    ActionStep(
                        action_type=ActionType.OPEN_APP,
                        target="Obsidian",
                        risk_level=RiskLevel.LOW,
                    )
                ],
            )
            context = FakeContextProvider().get_context()
            result = RecipePlanner(recipe).plan(WorkflowRequest(user_request="Run recipe"), context)
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.intent_summary, "Saved recipe: Writing mode")
        self.assertEqual(result.action_plan.steps[0].target, "Obsidian")

    def test_refinement_context_preserves_goal_current_plan_and_constraints(self) -> None:
        plan = ActionStep(
            action_type=ActionType.OPEN_APP,
            target="Notion",
            risk_level=RiskLevel.LOW,
            reason="Open notes.",
        )

        context = build_plan_refinement_context(
            original_goal="Start writing",
            current_plan=ActionPlan(plan_name="writing", source="test", steps=[plan]),
            user_refinement="不要打开 Notion，改成 Obsidian",
            recipe_id="recipe-1",
            revision_index=2,
        )

        self.assertEqual(context.original_goal, "Start writing")
        self.assertEqual(context.current_plan.steps[0].target, "Notion")
        self.assertEqual(context.recipe_id, "recipe-1")
        self.assertEqual(context.revision_index, 2)
        self.assertIn("不要打开 Notion", context.constraints[0])

    def test_check_recipe_reports_disabled_capability_and_missing_path_warning(self) -> None:
        recipe = WorkflowRecipe(
            name="Workspace",
            user_goal="Restore workspace",
            plan=ActionPlan(
                plan_name="workspace",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.RESTORE_WORKSPACE,
                        target="default",
                        risk_level=RiskLevel.MEDIUM,
                    ),
                    ActionStep(
                        action_type=ActionType.OPEN_FOLDER,
                        target="D:/DefinitelyMissing",
                        risk_level=RiskLevel.LOW,
                    ),
                ],
            ),
            risk_level=RiskLevel.MEDIUM,
        )

        result = check_recipe(
            recipe,
            capability_registry=CapabilityRegistry.default(),
            available_handler_names={"windows.open_folder"},
            path_exists=lambda _path: False,
        )

        self.assertFalse(result.ok)
        self.assertIn("CAPABILITY_DISABLED", [issue.code for issue in result.issues])
        self.assertIn("PATH_MISSING", [issue.code for issue in result.issues])
        self.assertTrue(any(issue.severity == "warning" for issue in result.issues))

    def test_recipe_display_text_is_product_language(self) -> None:
        recipe = WorkflowRecipe(
            name="写作环境",
            user_goal="开始写作",
            plan=ActionPlan(
                plan_name="writing",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.OPEN_APP,
                        target="Obsidian",
                        risk_level=RiskLevel.LOW,
                        reason="Open notes.",
                    )
                ],
            ),
            risk_level=RiskLevel.LOW,
        )

        label = recipe_label(recipe)
        detail = recipe_detail_text(recipe)

        self.assertIn("低风险", label)
        self.assertIn("1 个动作", label)
        self.assertIn("方案：写作环境", detail)
        self.assertIn("打开应用：Obsidian", detail)
        self.assertNotIn("open_app ->", detail)


if __name__ == "__main__":
    unittest.main()
