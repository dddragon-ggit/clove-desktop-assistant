from __future__ import annotations

import json
import unittest
import sys
from typing import Any
from pathlib import Path
from uuid import uuid4

import httpx

from desktop_assistant.adapters.windows_app_discovery import (
    ApplicationInventory,
    ApplicationInventoryStore,
    DiscoveredApplication,
)
from desktop_assistant.config import ModelProviderConfig
from desktop_assistant.models import ContextSnapshot, IntentInterpretation, PlannerResult, PolicyDecision, RiskLevel, WorkflowRequest
from desktop_assistant.adapters.openai_responses import (
    OpenAIResponsesClient,
    ProviderResponseError,
    ProviderTransportError,
    RealPlanner,
    RealReviewer,
    app_intent_match_schema,
    intent_interpretation_schema,
    planner_result_schema,
    review_result_schema,
)


def build_mock_client(expected_payload: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(expected_payload, ensure_ascii=False),
                            }
                        ],
                    }
                ]
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def build_sequence_mock_client(expected_payloads: list[dict]) -> httpx.Client:
    payloads = list(expected_payloads)

    def handler(request: httpx.Request) -> httpx.Response:
        if not payloads:
            return httpx.Response(500, request=request, text="No mock payload left.")
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(payloads.pop(0), ensure_ascii=False),
                            }
                        ],
                    }
                ]
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def expected_intent(**overrides: Any) -> dict:
    payload = IntentInterpretation(
        user_goal="Prepare weekly report workspace.",
        primary_intent="workspace_prepare",
        target_kind="workspace",
        target_name="weekly report",
        confidence="high",
        needs_clarification=False,
        clarification_question=None,
        reasoning_summary="The request asks for a work setup.",
    ).model_dump(mode="json")
    payload.update(overrides)
    return payload


def expected_app_match(**overrides: Any) -> dict:
    payload = {
        "local_app_request": True,
        "action_type": "open_app",
        "target_name": "QQ",
        "confidence": "high",
        "needs_clarification": False,
        "clarification_question": None,
        "reasoning_summary": "The user asked to open a local installed app.",
    }
    payload.update(overrides)
    return payload


def output_text_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"output_text": json.dumps(payload, ensure_ascii=False)},
    )


def schema_contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(schema_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(schema_contains_key(item, key) for item in value)
    return False


def assert_strict_objects(test_case: unittest.TestCase, value: Any) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object" and "properties" in value:
            test_case.assertIs(value.get("additionalProperties"), False)
            test_case.assertEqual(set(value.get("required", [])), set(value["properties"]))
        for item in value.values():
            assert_strict_objects(test_case, item)
    elif isinstance(value, list):
        for item in value:
            assert_strict_objects(test_case, item)


class OpenAIResponsesAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ModelProviderConfig(
            provider_name="OpenAI",
            base_url="https://example.com",
            wire_api="responses",
            model="gpt-5.4",
            review_model="gpt-5.4",
            model_reasoning_effort="xhigh",
            disable_response_storage=True,
            requires_openai_auth=True,
            api_key="sk-test",
        )
        self.context = ContextSnapshot(
            local_time="2026-04-26T19:00:00",
            date_label="2026-04-26",
            weekday="Sunday",
            timezone="Asia/Shanghai",
            weather="rainy",
            holiday=False,
        )

    def _inventory_store(self, apps: list[DiscoveredApplication]) -> tuple[ApplicationInventoryStore, Path]:
        base = Path.cwd() / "runtime" / "test_app_inventory"
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{uuid4().hex}.json"
        store = ApplicationInventoryStore(path=path)
        store.save(ApplicationInventory(generated_at="2026-04-27T00:00:00+00:00", applications=apps))
        return store, path

    def test_custom_schemas_are_strict_provider_compatible(self) -> None:
        for schema in [
            app_intent_match_schema(),
            intent_interpretation_schema(),
            planner_result_schema(),
            review_result_schema(),
        ]:
            with self.subTest(schema=schema):
                self.assertFalse(schema_contains_key(schema, "$defs"))
                self.assertFalse(schema_contains_key(schema, "$ref"))
                self.assertFalse(schema_contains_key(schema, "default"))
                self.assertFalse(schema_contains_key(schema, "anyOf"))
                assert_strict_objects(self, schema)

    def test_real_planner_parses_structured_response(self) -> None:
        expected = PlannerResult(
            intent_summary="Plan weekly report",
            requires_clarification=False,
            action_plan={
                "plan_name": "weekly-report-setup",
                "source": "provider",
                "steps": [
                    {
                        "action_type": "open_app",
                        "target": "Notion",
                        "params": {},
                        "risk_level": "low",
                        "reason": "Open the report editor.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Structured output test.",
        ).model_dump(mode="json")

        client = OpenAIResponsesClient(self.config, client=build_sequence_mock_client([expected_intent(), expected]))
        planner = RealPlanner(client, enable_fast_inventory=False)
        result = planner.plan(WorkflowRequest(user_request="开始做周报"), self.context)

        self.assertEqual(result.intent_summary, "Plan weekly report")
        self.assertEqual(result.action_plan.steps[0].target, "Notion")
        self.assertIsNotNone(result.intent_interpretation)
        self.assertEqual(result.intent_interpretation.primary_intent, "workspace_prepare")
        self.assertEqual(result.selected_intent_template, "intent.default")
        self.assertEqual(result.selected_planner_template, "planner.workspace")

    def test_real_planner_sends_custom_strict_schema(self) -> None:
        expected = PlannerResult(
            intent_summary="Plan weekly report",
            requires_clarification=False,
            action_plan={
                "plan_name": "weekly-report-setup",
                "source": "provider",
                "steps": [
                    {
                        "action_type": "open_app",
                        "target": "Notion",
                        "risk_level": "low",
                        "reason": "Open the report editor.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Structured output test.",
        ).model_dump(mode="json")
        seen: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            seen.append(body)
            schema_name = body["text"]["format"]["name"]
            response_payload = expected_intent() if schema_name == "intent_interpretation" else expected
            return httpx.Response(200, json={"output_text": json.dumps(response_payload, ensure_ascii=False)})

        client = OpenAIResponsesClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))
        planner = RealPlanner(client, enable_fast_inventory=False)
        planner.plan(WorkflowRequest(user_request="开始做周报"), self.context)

        self.assertEqual(seen[0]["text"]["format"]["schema"], intent_interpretation_schema())
        self.assertTrue(seen[0]["text"]["format"]["strict"])
        intent_payload = json.loads(seen[0]["input"][1]["content"])
        self.assertEqual(intent_payload["selected_prompt_template"], "intent.default")
        self.assertIn("intent_process", intent_payload)

        self.assertEqual(seen[1]["text"]["format"]["schema"], planner_result_schema())
        self.assertTrue(seen[1]["text"]["format"]["strict"])
        planner_payload = json.loads(seen[1]["input"][1]["content"])
        self.assertEqual(planner_payload["intent_interpretation"]["primary_intent"], "workspace_prepare")
        self.assertEqual(planner_payload["selected_prompt_template"], "planner.workspace")
        self.assertIn("capability_registry", planner_payload)
        self.assertIn("open_app", planner_payload["allowed_actions"])
        self.assertIn("planning_process", planner_payload)

    def test_real_planner_prefers_answer_query_for_web_lookup(self) -> None:
        expected = PlannerResult(
            intent_summary="Answer the weather query",
            requires_clarification=False,
            action_plan={
                "plan_name": "web-lookup",
                "source": "provider",
                "steps": [
                    {
                        "action_type": "answer_query",
                        "target": "查询今天西安天气",
                        "risk_level": "low",
                        "reason": "Fetch and summarize current weather information.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Use the web lookup capability.",
        ).model_dump(mode="json")
        seen_system_prompts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            seen_system_prompts.append(body["input"][0]["content"])
            schema_name = body["text"]["format"]["name"]
            response_payload = (
                expected_intent(
                    user_goal="查询今天西安天气",
                    primary_intent="web_lookup",
                    target_kind="query",
                    target_name="查询今天西安天气",
                )
                if schema_name == "intent_interpretation"
                else expected
            )
            return httpx.Response(200, json={"output_text": json.dumps(response_payload, ensure_ascii=False)})

        client = OpenAIResponsesClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))
        planner = RealPlanner(client, enable_fast_inventory=False)

        result = planner.plan(WorkflowRequest(user_request="查询今天西安天气"), self.context)

        self.assertEqual(result.selected_planner_template, "planner.web_lookup")
        self.assertEqual(result.action_plan.steps[0].action_type.value, "answer_query")
        self.assertEqual(result.action_plan.steps[0].target, "查询今天西安天气")
        self.assertIn("answer_query", seen_system_prompts[1])
        self.assertIn("prefer one answer_query step", seen_system_prompts[1])

    def test_real_planner_normalizes_single_answer_query_target_to_user_request(self) -> None:
        expected = PlannerResult(
            intent_summary="Answer the gold price query",
            requires_clarification=False,
            action_plan={
                "plan_name": "lookup-today-gold-price",
                "source": "provider",
                "steps": [
                    {
                        "action_type": "answer_query",
                        "target": "2026-04-26 今日黄金价格",
                        "risk_level": "low",
                        "reason": "Fetch and summarize current gold prices.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Use the web lookup capability.",
        ).model_dump(mode="json")
        client = OpenAIResponsesClient(
            self.config,
            client=build_sequence_mock_client(
                [
                    expected_intent(
                        user_goal="查询今天黄金价格",
                        primary_intent="web_lookup",
                        target_kind="query",
                        target_name="今天黄金价格",
                    ),
                    expected,
                ]
            ),
        )
        planner = RealPlanner(client, enable_fast_inventory=False)

        result = planner.plan(WorkflowRequest(user_request="查询今天黄金价格"), self.context)

        self.assertEqual(result.action_plan.steps[0].action_type.value, "answer_query")
        self.assertEqual(result.action_plan.steps[0].target, "查询今天黄金价格")

    def test_real_planner_normalizes_current_project_target(self) -> None:
        expected = PlannerResult(
            intent_summary="Open the current project folder",
            requires_clarification=False,
            action_plan={
                "plan_name": "open-current-project-folder",
                "source": "provider",
                "steps": [
                    {
                        "action_type": "open_project",
                        "target": "当前项目文件夹",
                        "risk_level": "low",
                        "reason": "Open the current project.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Use the project locator.",
        ).model_dump(mode="json")
        client = OpenAIResponsesClient(
            self.config,
            client=build_sequence_mock_client(
                [
                    expected_intent(
                        user_goal="打开当前项目文件夹",
                        primary_intent="open_file_or_folder",
                        target_kind="workspace",
                        target_name="当前项目文件夹",
                    ),
                    expected,
                ]
            ),
        )
        planner = RealPlanner(client, enable_fast_inventory=False)

        result = planner.plan(WorkflowRequest(user_request="打开当前项目文件夹"), self.context)

        self.assertEqual(result.action_plan.steps[0].action_type.value, "open_project")
        self.assertEqual(result.action_plan.steps[0].target, "current workspace")

    def test_real_planner_normalizes_list_windows_target(self) -> None:
        expected = PlannerResult(
            intent_summary="List visible desktop windows",
            requires_clarification=False,
            action_plan={
                "plan_name": "list-windows",
                "source": "provider",
                "steps": [
                    {
                        "action_type": "list_windows",
                        "target": "当前桌面可见窗口",
                        "risk_level": "low",
                        "reason": "Inspect current visible windows.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Use the window state capability.",
        ).model_dump(mode="json")
        client = OpenAIResponsesClient(
            self.config,
            client=build_sequence_mock_client(
                [
                    expected_intent(
                        user_goal="列出当前窗口",
                        primary_intent="manage_window",
                        target_kind="window",
                        target_name="当前窗口",
                    ),
                    expected,
                ]
            ),
        )
        planner = RealPlanner(client, enable_fast_inventory=False)

        result = planner.plan(WorkflowRequest(user_request="列出当前窗口"), self.context)

        self.assertEqual(result.action_plan.steps[0].action_type.value, "list_windows")
        self.assertEqual(result.action_plan.steps[0].target, "visible")

    def test_real_planner_blocks_unsupported_destructive_file_request_without_provider_call(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(500, request=request, text="should not be called")

        client = OpenAIResponsesClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))
        planner = RealPlanner(client, enable_fast_inventory=False)

        result = planner.plan(WorkflowRequest(user_request="帮我删除桌面旧文件并清空回收站"), self.context)

        self.assertEqual(calls, 0)
        self.assertTrue(result.requires_clarification)
        self.assertEqual(result.risk_guess, RiskLevel.HIGH)
        self.assertEqual(result.action_plan.steps, [])

    def test_real_planner_grounds_open_app_steps_from_inventory(self) -> None:
        expected = PlannerResult(
            intent_summary="Open local Python app",
            requires_clarification=False,
            action_plan={
                "plan_name": "open-python",
                "source": "provider",
                "steps": [
                    {
                        "action_type": "open_app",
                        "target": "python",
                        "risk_level": "low",
                        "reason": "Open the local app.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Structured output test.",
        ).model_dump(mode="json")
        client = OpenAIResponsesClient(
            self.config,
            client=build_sequence_mock_client(
                [
                    expected_intent(
                        primary_intent="open_local_app",
                        target_kind="local_app",
                        target_name="python",
                    ),
                    expected,
                ]
            ),
        )
        planner = RealPlanner(client, enable_fast_inventory=False)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Python App",
                    executable_path=sys.executable,
                    functions=("development",),
                    source="test",
                )
            ]
        )
        planner.app_inventory_store = store
        try:
            result = planner.plan(WorkflowRequest(user_request="打开 Python 应用"), self.context)
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.action_plan.steps[0].target, "Python App")
        self.assertEqual(result.action_plan.steps[0].params["executable_path"], sys.executable)

    def test_real_planner_uses_model_app_match_before_inventory_plan(self) -> None:
        seen: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            seen.append(body)
            return httpx.Response(200, json={"output_text": json.dumps(expected_app_match(), ensure_ascii=False)})

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        planner = RealPlanner(client)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="QQ",
                    executable_path=sys.executable,
                    functions=("communication",),
                    source="test",
                )
            ]
        )
        planner.app_inventory_store = store
        try:
            result = planner.plan(WorkflowRequest(user_request="\u6253\u5f00QQ"), self.context)
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.action_plan.source, "model_inventory_path")
        self.assertEqual(result.action_plan.steps[0].action_type.value, "open_app")
        self.assertEqual(result.action_plan.steps[0].target, "QQ")
        self.assertEqual(result.action_plan.steps[0].params["executable_path"], sys.executable)
        self.assertEqual(seen[0]["text"]["format"]["schema"], app_intent_match_schema())
        app_match_payload = json.loads(seen[0]["input"][1]["content"])
        self.assertIn("QQ", app_match_payload["app_name_index_summary"])
        self.assertIn("QQ", app_match_payload["candidate_app_summary"])

    def test_real_planner_sends_relevant_app_candidates_to_model_matcher(self) -> None:
        seen_payloads: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            seen_payloads.append(json.loads(body["input"][1]["content"]))
            return httpx.Response(
                200,
                json={"output_text": json.dumps(expected_app_match(target_name="暴雪战网"), ensure_ascii=False)},
            )

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        planner = RealPlanner(client)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="暴雪战网",
                    executable_path=sys.executable,
                    functions=("general_app",),
                    source="test",
                ),
                DiscoveredApplication(
                    name="QQ",
                    executable_path=sys.executable,
                    functions=("communication",),
                    source="test",
                ),
            ]
        )
        planner.app_inventory_store = store
        try:
            result = planner.plan(
                WorkflowRequest(user_request="\u6253\u5f00\u6218\u7f51\u5e94\u7528"),
                self.context,
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.action_plan.steps[0].target, "暴雪战网")
        self.assertIn("暴雪战网", seen_payloads[0]["candidate_app_summary"])
        self.assertNotIn("QQ |", seen_payloads[0]["candidate_app_summary"])

    def test_real_planner_falls_back_to_deterministic_inventory_when_app_match_provider_fails(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline", request=request)

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=0,
        )
        planner = RealPlanner(client)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="QQ",
                    executable_path=sys.executable,
                    functions=("communication",),
                    source="test",
                )
            ]
        )
        planner.app_inventory_store = store
        try:
            result = planner.plan(WorkflowRequest(user_request="\u6253\u5f00QQ"), self.context)
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.action_plan.source, "inventory_fast_path")
        self.assertEqual(result.action_plan.steps[0].target, "QQ")

    def test_real_planner_grounds_low_confidence_model_app_match_before_clarifying(self) -> None:
        client = OpenAIResponsesClient(
            self.config,
            client=build_mock_client(
                expected_app_match(
                    target_name="\u6218\u7f51\u5e94\u7528",
                    confidence="low",
                    reasoning_summary="The name is informal but resembles an installed app.",
                )
            ),
        )
        planner = RealPlanner(client)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="\u66b4\u96ea\u6218\u7f51",
                    executable_path=sys.executable,
                    functions=("general_app",),
                    source="test",
                )
            ]
        )
        planner.app_inventory_store = store
        try:
            result = planner.plan(
                WorkflowRequest(user_request="\u6253\u5f00\u6218\u7f51\u5e94\u7528"),
                self.context,
            )
        finally:
            if path.exists():
                path.unlink()

        self.assertFalse(result.requires_clarification)
        self.assertEqual(result.action_plan.source, "model_inventory_path")
        self.assertEqual(result.action_plan.steps[0].target, "\u66b4\u96ea\u6218\u7f51")

    def test_real_reviewer_fast_approves_inventory_fast_path_without_provider_call(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.fail("Fast local review should not call the provider.")

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        reviewer = RealReviewer(client)
        planner_result = PlannerResult(
            intent_summary="Open installed local application: QQ",
            requires_clarification=False,
            action_plan={
                "plan_name": "fast-open-local-app",
                "source": "inventory_fast_path",
                "steps": [
                    {
                        "action_type": "open_app",
                        "target": "QQ",
                        "params": {"executable_path": sys.executable},
                        "risk_level": "low",
                        "reason": "Fast local inventory match.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Fast path.",
        )
        policy_decision = PolicyDecision(
            approved=True,
            risk_level=RiskLevel.LOW,
            requires_user_confirmation=False,
            issues=[],
        )

        result = reviewer.review(
            WorkflowRequest(user_request="\u6253\u5f00QQ"),
            planner_result,
            policy_decision,
            self.context,
        )

        self.assertTrue(result.approved)
        self.assertIn("Fast local review", result.review_summary)

    def test_real_reviewer_rejects_clarification_without_provider_call(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.fail("Clarification review should not call the provider.")

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        reviewer = RealReviewer(client)
        planner_result = PlannerResult(
            intent_summary="Need clarification before cleanup.",
            requires_clarification=True,
            action_plan={
                "plan_name": "clarify-destructive-file-operation",
                "source": "safety_normalizer",
                "steps": [],
            },
            risk_guess="high",
            reasoning_summary="No executable steps.",
        )
        policy_decision = PolicyDecision(
            approved=False,
            risk_level=RiskLevel.HIGH,
            requires_user_confirmation=True,
            issues=[],
        )

        result = reviewer.review(
            WorkflowRequest(user_request="帮我删除桌面旧文件并清空回收站"),
            planner_result,
            policy_decision,
            self.context,
        )

        self.assertFalse(result.approved)
        self.assertEqual(result.risk_level, RiskLevel.HIGH)
        self.assertTrue(result.needs_user_confirmation)
        self.assertIn("no executable steps", " ".join(result.issues).lower())

    def test_real_planner_uses_configured_inventory_store_for_prompt_summary(self) -> None:
        expected = PlannerResult(
            intent_summary="Open inventory app",
            requires_clarification=False,
            action_plan={
                "plan_name": "open-inventory-app",
                "source": "provider",
                "steps": [
                    {
                        "action_type": "open_app",
                        "target": "Needle",
                        "risk_level": "low",
                        "reason": "Open the local app.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Structured output test.",
        ).model_dump(mode="json")
        seen_system_prompts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            seen_system_prompts.append(body["input"][0]["content"])
            schema_name = body["text"]["format"]["name"]
            response_payload = (
                expected_intent(
                    primary_intent="open_local_app",
                    target_kind="local_app",
                    target_name="Needle",
                )
                if schema_name == "intent_interpretation"
                else expected
            )
            return httpx.Response(200, json={"output_text": json.dumps(response_payload, ensure_ascii=False)})

        client = OpenAIResponsesClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))
        planner = RealPlanner(client, enable_fast_inventory=False)
        store, path = self._inventory_store(
            [
                DiscoveredApplication(
                    name="Needle App",
                    executable_path=sys.executable,
                    functions=("development",),
                    source="test",
                )
            ]
        )
        planner.app_inventory_store = store
        try:
            result = planner.plan(WorkflowRequest(user_request="open Needle app"), self.context)
        finally:
            if path.exists():
                path.unlink()

        self.assertEqual(result.action_plan.steps[0].target, "Needle App")
        self.assertEqual(len(seen_system_prompts), 2)
        self.assertTrue(all("Needle App" in prompt for prompt in seen_system_prompts))

    def test_real_reviewer_parses_structured_response(self) -> None:
        expected = {
            "approved": True,
            "risk_level": "low",
            "needs_user_confirmation": False,
            "review_summary": "Looks safe.",
            "issues": [],
            "rejection_reason": None,
        }
        client = OpenAIResponsesClient(self.config, client=build_mock_client(expected))
        reviewer = RealReviewer(client)
        planner_result = PlannerResult(
            intent_summary="Plan weekly report",
            requires_clarification=False,
            action_plan={
                "plan_name": "weekly-report-setup",
                "source": "provider",
                "steps": [
                    {
                        "action_type": "open_app",
                        "target": "Notion",
                        "params": {},
                        "risk_level": "low",
                        "reason": "Open the report editor.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Structured output test.",
        )
        policy_decision = PolicyDecision(
            approved=True,
            risk_level=RiskLevel.LOW,
            requires_user_confirmation=False,
            issues=[],
        )

        result = reviewer.review(
            WorkflowRequest(user_request="开始做周报"),
            planner_result,
            policy_decision,
            self.context,
        )

        self.assertTrue(result.approved)
        self.assertEqual(result.review_summary, "Looks safe.")

    def test_real_reviewer_sends_custom_strict_schema(self) -> None:
        expected = {
            "approved": True,
            "risk_level": "low",
            "needs_user_confirmation": False,
            "review_summary": "Looks safe.",
            "issues": [],
            "rejection_reason": None,
        }
        seen: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            seen.append(body)
            return httpx.Response(200, json={"output_text": json.dumps(expected, ensure_ascii=False)})

        client = OpenAIResponsesClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))
        reviewer = RealReviewer(client)
        planner_result = PlannerResult(
            intent_summary="Plan weekly report",
            requires_clarification=False,
            action_plan={
                "plan_name": "weekly-report-setup",
                "source": "provider",
                "steps": [
                    {
                        "action_type": "open_app",
                        "target": "Notion",
                        "risk_level": "low",
                        "reason": "Open the report editor.",
                    }
                ],
            },
            risk_guess="low",
            reasoning_summary="Structured output test.",
        )
        policy_decision = PolicyDecision(
            approved=True,
            risk_level=RiskLevel.LOW,
            requires_user_confirmation=False,
            issues=[],
        )

        reviewer.review(
            WorkflowRequest(user_request="开始做周报"),
            planner_result,
            policy_decision,
            self.context,
        )

        self.assertEqual(seen[0]["text"]["format"]["schema"], review_result_schema())
        self.assertTrue(seen[0]["text"]["format"]["strict"])
        reviewer_payload = json.loads(seen[0]["input"][1]["content"])
        self.assertEqual(reviewer_payload["selected_prompt_template"], "reviewer.default")
        self.assertIn("review_process", reviewer_payload)

    def test_retries_retryable_status_before_success(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(502, request=request, text="bad gateway")
            return output_text_response({"ok": True})

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=2,
            retry_backoff_seconds=0,
        )

        result = client.create_json_response(
            model="gpt-5.4",
            system_prompt="Return JSON.",
            user_payload={"case": "retry"},
            schema_name="retry_test",
            schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, 3)

    def test_retries_connect_error_before_success(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("simulated connect error", request=request)
            return output_text_response({"ok": True})

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=1,
            retry_backoff_seconds=0,
        )

        result = client.create_json_response(
            model="gpt-5.4",
            system_prompt="Return JSON.",
            user_payload={"case": "connect_retry"},
            schema_name="retry_test",
            schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, 2)

    def test_retries_timeout_before_success(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ReadTimeout("simulated timeout", request=request)
            return output_text_response({"ok": True})

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=1,
            retry_backoff_seconds=0,
        )

        result = client.create_json_response(
            model="gpt-5.4",
            system_prompt="Return JSON.",
            user_payload={"case": "timeout_retry"},
            schema_name="retry_test",
            schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, 2)

    def test_retries_remote_protocol_error_before_success(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.RemoteProtocolError("server disconnected", request=request)
            return output_text_response({"ok": True})

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=1,
            retry_backoff_seconds=0,
        )

        result = client.create_json_response(
            model="gpt-5.4",
            system_prompt="Return JSON.",
            user_payload={"case": "remote_protocol_retry"},
            schema_name="retry_test",
            schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, 2)

    def test_primary_error_uses_single_fallback_path(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            if isinstance(body.get("input"), list):
                calls.append("primary")
                return httpx.Response(400, request=request, text="strict schema rejected")
            calls.append("fallback")
            return output_text_response({"ok": True})

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=1,
            retry_backoff_seconds=0,
        )

        result = client.create_json_response(
            model="gpt-5.4",
            system_prompt="Return JSON.",
            user_payload={"case": "fallback"},
            schema_name="fallback_test",
            schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, ["primary", "fallback"])

    def test_json_parser_accepts_fenced_fallback_output(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"output_text": "```json\n{\"ok\": true}\n```"})

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            retry_backoff_seconds=0,
        )

        result = client.create_json_response(
            model="gpt-5.4",
            system_prompt="Return JSON.",
            user_payload={"case": "fenced_json"},
            schema_name="fenced_test",
            schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        )

        self.assertEqual(result, {"ok": True})

    def test_exhausted_network_error_is_clear(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ConnectError("simulated connect error", request=request)

        client = OpenAIResponsesClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=1,
            retry_backoff_seconds=0,
        )

        with self.assertRaisesRegex(ProviderTransportError, "network_test structured request failed after 2 attempts"):
            client.create_json_response(
                model="gpt-5.4",
                system_prompt="Return JSON.",
                user_payload={"case": "network_down"},
                schema_name="network_test",
                schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
            )

        self.assertEqual(calls, 2)


if __name__ == "__main__":
    unittest.main()
