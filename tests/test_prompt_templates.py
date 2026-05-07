from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from desktop_assistant.adapters.windows_app_discovery import (
    ApplicationInventory,
    ApplicationInventoryStore,
    DiscoveredApplication,
)
from desktop_assistant.models import ActionPlan, ActionStep, ActionType, ContextSnapshot, IntentInterpretation, RiskLevel, WorkflowRequest
from desktop_assistant.prompt_templates import (
    PromptTemplateLibrary,
    load_app_candidate_summary,
    load_app_inventory_summary,
    load_app_name_index_summary,
)
from desktop_assistant.recipes import build_plan_refinement_context


class PromptTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ContextSnapshot(
            local_time="2026-04-27T16:00:00",
            date_label="2026-04-27",
            weekday="Monday",
            timezone="Asia/Shanghai",
        )

    def _inventory_path(self) -> Path:
        base = Path.cwd() / "runtime" / "test_app_inventory"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{uuid4().hex}.json"

    def test_planner_selects_web_lookup_template_for_weather(self) -> None:
        library = PromptTemplateLibrary.default()
        rendered = library.render_planner_prompt(
            request=WorkflowRequest(user_request="查询今天西安天气"),
            context=self.context,
            allowed_actions=["answer_query", "open_url", "open_app"],
            app_inventory_summary="No apps.",
            capability_summary="- answer_query: Fetch and summarize current information.\n- open_url: Open a web URL.",
        )

        self.assertEqual(rendered.template_id, "planner.web_lookup")
        self.assertIn("Information lookup template", rendered.system_prompt)
        self.assertIn("answer_query", rendered.system_prompt)
        self.assertIn("open_url", rendered.system_prompt)
        self.assertIn("Capability registry summary", rendered.system_prompt)

    def test_intent_prompt_prefers_local_app_for_app_wording(self) -> None:
        rendered = PromptTemplateLibrary.default().render_intent_prompt(
            request=WorkflowRequest(user_request="打开战网应用"),
            app_inventory_summary="- 暴雪战网 | functions=general_app | executable=D:\\battle_net\\Battle.net\\Battle.net.exe",
            capability_summary="- open_app: Open an installed Windows application.",
        )

        self.assertEqual(rendered.template_id, "intent.local_app")
        self.assertIn("Local app intent template", rendered.system_prompt)
        self.assertIn("战网", rendered.system_prompt)
        self.assertIn("open_app", rendered.system_prompt)

    def test_app_match_prompt_uses_name_index_only(self) -> None:
        rendered = PromptTemplateLibrary.default().render_app_match_prompt(
            request=WorkflowRequest(user_request="\u6253\u5f00QQ"),
            app_name_index_summary="generated_at=now; count=1\n- QQ",
            candidate_app_summary="High-relevance app candidates for this request:\n- QQ | functions=communication | executable=D:\\qq\\QQ.exe",
        )

        self.assertEqual(rendered.template_id, "app_match.local_app")
        self.assertIn("lightweight app-intent matcher", rendered.system_prompt)
        self.assertIn("High-relevance candidates", rendered.system_prompt)
        self.assertIn("- QQ", rendered.system_prompt)

    def test_planner_template_uses_intent_interpretation_over_keywords(self) -> None:
        rendered = PromptTemplateLibrary.default().render_planner_prompt(
            request=WorkflowRequest(user_request="打开战网应用"),
            context=self.context,
            allowed_actions=["open_url", "open_app"],
            app_inventory_summary="- 暴雪战网 | functions=general_app | executable=D:\\battle_net\\Battle.net\\Battle.net.exe",
            intent_interpretation=IntentInterpretation(
                user_goal="打开本机战网客户端",
                primary_intent="open_local_app",
                target_kind="local_app",
                target_name="战网",
                confidence="high",
                needs_clarification=False,
                clarification_question=None,
                reasoning_summary="用户明确说应用。",
            ),
        )

        self.assertEqual(rendered.template_id, "planner.local_app")
        self.assertIn("Local application template", rendered.system_prompt)

    def test_planner_selects_window_management_template(self) -> None:
        rendered = PromptTemplateLibrary.default().render_planner_prompt(
            request=WorkflowRequest(user_request="最小化 Cursor 窗口"),
            context=self.context,
            allowed_actions=["list_windows", "minimize_window", "close_window"],
            app_inventory_summary="- Cursor | functions=development | executable=C:\\Cursor\\Cursor.exe",
            intent_interpretation=IntentInterpretation(
                user_goal="最小化 Cursor 窗口",
                primary_intent="window_management",
                target_kind="local_app",
                target_name="Cursor",
                confidence="high",
                needs_clarification=False,
                clarification_question=None,
                reasoning_summary="用户想改变现有窗口状态。",
            ),
        )

        self.assertEqual(rendered.template_id, "planner.window_management")
        self.assertIn("Window management template", rendered.system_prompt)
        self.assertIn("minimize_window", rendered.system_prompt)
        self.assertIn("close_window", rendered.system_prompt)

    def test_planner_prompt_includes_plan_refinement_context(self) -> None:
        refinement = build_plan_refinement_context(
            original_goal="Start writing",
            current_plan=ActionPlan(
                plan_name="writing",
                source="test",
                steps=[
                    ActionStep(
                        action_type=ActionType.OPEN_APP,
                        target="Notion",
                        risk_level=RiskLevel.LOW,
                        reason="Open notes.",
                    )
                ],
            ),
            user_refinement="不要打开 Notion，改成 Obsidian",
            revision_index=2,
        )
        rendered = PromptTemplateLibrary.default().render_planner_prompt(
            request=WorkflowRequest(
                user_request="Refine writing plan",
                plan_refinement=refinement,
            ),
            context=self.context,
            allowed_actions=["open_app", "open_url"],
            app_inventory_summary="- Obsidian | functions=writing | executable=C:\\Apps\\Obsidian.exe",
            capability_summary="- open_app: Open an installed Windows application.",
        )

        self.assertIn("Plan refinement context", rendered.system_prompt)
        self.assertIn("original_goal=Start writing", rendered.system_prompt)
        self.assertIn("user_refinement=不要打开 Notion", rendered.system_prompt)
        self.assertIn("open_app -> Notion", rendered.system_prompt)

    def test_reviewer_selects_execution_safety_template_for_open_request(self) -> None:
        rendered = PromptTemplateLibrary.default().render_reviewer_prompt(
            request=WorkflowRequest(user_request="帮我打开知乎")
        )

        self.assertEqual(rendered.template_id, "reviewer.execution_safety")
        self.assertIn("Execution safety review", rendered.system_prompt)

    def test_app_inventory_summary_uses_cached_file(self) -> None:
        path = self._inventory_path()
        store = ApplicationInventoryStore(path=path)
        try:
            store.save(
                ApplicationInventory(
                    generated_at="2026-04-27T00:00:00+00:00",
                    applications=[
                        DiscoveredApplication(
                            name="Obsidian",
                            executable_path="C:\\Apps\\Obsidian.exe",
                            functions=("writing",),
                            source="test",
                        )
                    ],
                )
            )
            summary = load_app_inventory_summary(path=path)
        finally:
            if path.exists():
                path.unlink()

        self.assertIn("Obsidian", summary)
        self.assertIn("functions=writing", summary)
        self.assertIn("C:\\Apps\\Obsidian.exe", summary)

    def test_app_inventory_summary_prepends_relevant_match_beyond_limit(self) -> None:
        path = self._inventory_path()
        store = ApplicationInventoryStore(path=path)
        filler_apps = [
            DiscoveredApplication(
                name=f"Filler {index}",
                executable_path=f"C:\\Apps\\Filler{index}.exe",
                functions=("general_app",),
                source="test",
            )
            for index in range(5)
        ]
        try:
            store.save(
                ApplicationInventory(
                    generated_at="2026-04-27T00:00:00+00:00",
                    applications=[
                        *filler_apps,
                        DiscoveredApplication(
                            name="暴雪战网",
                            executable_path="D:\\battle_net\\Battle.net\\Battle.net Launcher.exe",
                            functions=("general_app",),
                            source="test",
                        ),
                    ],
                )
            )
            summary = load_app_inventory_summary(path=path, limit=2, query="打开战网应用")
        finally:
            if path.exists():
                path.unlink()

        self.assertIn("Relevant app matches", summary)
        self.assertIn("暴雪战网", summary)
        self.assertIn("Battle.net Launcher.exe", summary)

    def test_app_inventory_summary_handles_corrupt_cache(self) -> None:
        path = self._inventory_path()
        path.write_text("{not json", encoding="utf-8")
        try:
            summary = load_app_inventory_summary(path=path)
        finally:
            if path.exists():
                path.unlink()

        self.assertIn("App inventory cache is unavailable", summary)

    def test_app_name_index_summary_uses_name_only_cache(self) -> None:
        path = self._inventory_path()
        store = ApplicationInventoryStore(path=path)
        try:
            store.save(
                ApplicationInventory(
                    generated_at="2026-04-27T00:00:00+00:00",
                    applications=[
                        DiscoveredApplication(
                            name="Obsidian",
                            executable_path="C:\\Apps\\Obsidian.exe",
                            functions=("writing",),
                            source="test",
                        )
                    ],
                )
            )
            summary = load_app_name_index_summary(
                path=path,
                name_index_path=store.name_index_path,
            )
        finally:
            if path.exists():
                path.unlink()
            if store.name_index_path.exists():
                store.name_index_path.unlink()

        self.assertIn("Obsidian", summary)
        self.assertNotIn("C:\\Apps\\Obsidian.exe", summary)
        self.assertNotIn("functions=writing", summary)

    def test_app_candidate_summary_highlights_relevant_alias_match(self) -> None:
        path = self._inventory_path()
        store = ApplicationInventoryStore(path=path)
        try:
            store.save(
                ApplicationInventory(
                    generated_at="2026-04-27T00:00:00+00:00",
                    applications=[
                        DiscoveredApplication(
                            name="暴雪战网",
                            executable_path="D:\\battle_net\\Battle.net\\Battle.net Launcher.exe",
                            functions=("general_app",),
                            source="test",
                        ),
                        DiscoveredApplication(
                            name="QQ",
                            executable_path="D:\\qq\\QQ.exe",
                            functions=("communication",),
                            source="test",
                        ),
                    ],
                )
            )
            summary = load_app_candidate_summary(
                query="打开战网应用",
                path=path,
                name_index_path=store.name_index_path,
            )
        finally:
            if path.exists():
                path.unlink()
            if store.name_index_path.exists():
                store.name_index_path.unlink()

        self.assertIn("High-relevance app candidates", summary)
        self.assertIn("暴雪战网", summary)
        self.assertIn("Battle.net Launcher.exe", summary)
        self.assertNotIn("QQ", summary)


if __name__ == "__main__":
    unittest.main()
