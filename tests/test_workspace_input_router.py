from __future__ import annotations

import unittest

from desktop_assistant.activity import ActivityApp, ActivityFile, ActivityProject, ActivitySnapshot
from desktop_assistant.habits import NextActionPrediction
from desktop_assistant.confirmation import ConfirmationChoice, ConfirmationService
from desktop_assistant.input_router import InputRouteType, InputRouter
from desktop_assistant.models import ActionPlan, ActionStep, ActionType, RiskLevel
from desktop_assistant.action_trust import ActionTrustStore
from desktop_assistant.todo import TodoItem, TodoWorkspaceHint
from desktop_assistant.workspace import WorkspaceDraftStore, WorkspaceService, WorkspaceSuggestionBuilder
from pathlib import Path
from shutil import rmtree
from uuid import uuid4


def _workspace_path() -> Path:
    base = Path.cwd() / "runtime" / "test_workspace"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


class WorkspaceSuggestionTests(unittest.TestCase):
    def test_todo_workspace_hint_becomes_action_plan(self) -> None:
        todo = TodoItem(
            title="写周报",
            needs_computer=True,
            workspace=TodoWorkspaceHint(
                apps=["Cursor"],
                urls=["https://example.com"],
                projects=["desktop_assistant"],
            ),
        )

        suggestion = WorkspaceSuggestionBuilder().from_todo(todo)

        self.assertTrue(suggestion.has_actions())
        self.assertEqual([step.action_type for step in suggestion.plan.steps], [
            ActionType.OPEN_APP,
            ActionType.OPEN_URL,
            ActionType.OPEN_PROJECT,
        ])

    def test_todo_title_can_infer_basic_workspace_resource(self) -> None:
        suggestion = WorkspaceSuggestionBuilder().from_todo(TodoItem(title="打开 https://example.com"))

        self.assertTrue(suggestion.has_actions())
        self.assertEqual(suggestion.title, "工作区建议：打开 https://example.com")
        self.assertEqual(suggestion.plan.steps[0].action_type, ActionType.OPEN_URL)

    def test_todo_description_participates_in_workspace_inference(self) -> None:
        suggestion = WorkspaceSuggestionBuilder().from_todo(
            TodoItem(title="准备评审", description="材料在 https://example.com/review")
        )

        self.assertTrue(suggestion.has_actions())
        self.assertEqual(suggestion.plan.steps[0].target, "https://example.com/review")

    def test_continue_from_activity_reopens_project_file_and_focuses_app(self) -> None:
        activity = ActivitySnapshot(
            active_app=ActivityApp(name="Cursor"),
            active_file=ActivityFile(name="main.py", path=r"D:\repo\main.py"),
            active_project=ActivityProject(name="repo", path=r"D:\repo"),
        )

        suggestion = WorkspaceSuggestionBuilder().continue_from_activity(activity)

        self.assertEqual(suggestion.title, "继续刚才的工作")
        self.assertEqual([step.action_type for step in suggestion.plan.steps], [
            ActionType.OPEN_PROJECT,
            ActionType.OPEN_FILE,
            ActionType.FOCUS_APP,
        ])

    def test_workspace_service_refines_and_saves_recipe(self) -> None:
        from desktop_assistant.recipe import RecipeStore

        root = _workspace_path()
        try:
            builder = WorkspaceSuggestionBuilder()
            suggestion = builder.from_goal("打开 https://example.com")
            service = WorkspaceService(builder=builder, recipe_store=RecipeStore(root / "recipes.json"))

            refined = service.refine(suggestion, "再打开 https://openai.com")
            recipe = service.save_as_recipe(refined, name="研究环境")

            self.assertEqual(len(refined.plan.steps), 2)
            self.assertEqual(recipe.name, "研究环境")
        finally:
            rmtree(root, ignore_errors=True)

    def test_workspace_refine_preserves_identity_and_feedback_history(self) -> None:
        root = _workspace_path()
        try:
            service = WorkspaceService(draft_store=WorkspaceDraftStore(root / "drafts.json"))
            suggestion = service.save_draft(service.builder.from_goal("打开 https://example.com"))

            refined = service.refine(suggestion, "再打开 https://openai.com")
            pending = service.pending_draft(suggestion.id)

            self.assertEqual(refined.id, suggestion.id)
            self.assertEqual(refined.created_at, suggestion.created_at)
            self.assertEqual(refined.user_feedback, ["再打开 https://openai.com"])
            self.assertIsNotNone(pending)
            self.assertEqual(pending.id, suggestion.id)
            self.assertEqual(len(pending.plan.steps), 2)
        finally:
            rmtree(root, ignore_errors=True)


class InputRouterTests(unittest.TestCase):
    def test_input_router_accepts_prediction_with_tab(self) -> None:
        prediction = NextActionPrediction(
            suggested_text="继续项目：repo",
            route_hint="continue_work",
            confidence="medium",
            source="active_project",
        )

        route = InputRouter().route("", prediction=prediction, accepted_prediction=True)

        self.assertEqual(route.route_type, InputRouteType.CONTINUE_WORK)
        self.assertTrue(route.accepted_prediction)
        self.assertEqual(route.normalized_text, "继续项目：repo")

    def test_input_router_completes_vague_continue_with_prediction(self) -> None:
        prediction = NextActionPrediction(
            suggested_text="继续：desktop_assistant 的 UI 设计",
            route_hint="continue_work",
            confidence="low",
            source="context_completion",
        )

        route = InputRouter().route("继续", prediction=prediction)

        self.assertEqual(route.route_type, InputRouteType.CONTINUE_WORK)
        self.assertEqual(route.source, "context_prediction")
        self.assertEqual(route.normalized_text, "继续：desktop_assistant 的 UI 设计")

    def test_input_router_sends_unknown_text_to_dialog(self) -> None:
        route = InputRouter().route("我有个复杂想法，先聊聊")

        self.assertEqual(route.route_type, InputRouteType.DIALOG)

    def test_input_router_detects_todo_and_workspace_keywords(self) -> None:
        router = InputRouter()

        self.assertEqual(router.route("查看待办任务清单").route_type, InputRouteType.TODO)
        self.assertEqual(router.route("帮我准备工作环境").route_type, InputRouteType.WORKSPACE)
        self.assertEqual(router.route("打开 https://example.com").route_type, InputRouteType.WORKSPACE)


class ConfirmationServiceTests(unittest.TestCase):
    def test_confirmation_flow_can_trust_medium_risk_action(self) -> None:
        root = _workspace_path()
        try:
            trust_store = ActionTrustStore(root / "trust.json")
            plan = ActionPlan(
                plan_name="close-window",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.CLOSE_WINDOW,
                        target="QQ",
                        risk_level=RiskLevel.MEDIUM,
                    )
                ],
            )
            service = ConfirmationService(trust_store=trust_store)
            flow = service.build_flow(plan)
            result = service.apply_choice(plan, ConfirmationChoice.TRUST_ALWAYS)

            self.assertTrue(flow.requires_user_confirmation)
            self.assertIn(ConfirmationChoice.TRUST_ALWAYS, flow.choices)
            self.assertTrue(result.accepted)
            self.assertEqual(len(trust_store.trusted_keys()), 1)
        finally:
            rmtree(root, ignore_errors=True)

    def test_confirmation_flow_reloads_trusted_keys_after_trust_always(self) -> None:
        root = _workspace_path()
        try:
            trust_store = ActionTrustStore(root / "trust.json")
            plan = ActionPlan(
                plan_name="close-window",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.CLOSE_WINDOW,
                        target="QQ",
                        risk_level=RiskLevel.MEDIUM,
                    )
                ],
            )
            service = ConfirmationService(trust_store=trust_store)

            first_flow = service.build_flow(plan)
            service.apply_choice(plan, ConfirmationChoice.TRUST_ALWAYS)
            second_flow = service.build_flow(plan)

            self.assertTrue(first_flow.requires_user_confirmation)
            self.assertTrue(first_flow.action_cards[0].requires_confirmation)
            self.assertFalse(second_flow.requires_user_confirmation)
            self.assertTrue(second_flow.action_cards[0].whitelisted)
            self.assertFalse(second_flow.action_cards[0].requires_confirmation)
        finally:
            rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
