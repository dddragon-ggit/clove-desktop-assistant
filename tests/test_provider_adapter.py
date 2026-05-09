from __future__ import annotations

import json
import unittest
from typing import Any

import httpx

from desktop_assistant.adapters.anthropic_client import AnthropicClient
from desktop_assistant.adapters.openai_client import OpenAIResponsesClient, ProviderResponseError, ProviderTransportError
from desktop_assistant.adapters.provider_factory import LLMClient, create_client
from desktop_assistant.config import ModelProviderConfig


def _openai_config(**overrides: Any) -> ModelProviderConfig:
    defaults = dict(
        provider_name="OpenAI",
        base_url="https://api.openai.com",
        wire_api="responses",
        model="gpt-4o",
        review_model="gpt-4o",
        api_key="sk-test-key",
    )
    defaults.update(overrides)
    return ModelProviderConfig(**defaults)


def _anthropic_config(**overrides: Any) -> ModelProviderConfig:
    defaults = dict(
        provider_name="Mimo",
        base_url="https://token-plan-cn.xiaomimimo.com/anthropic",
        wire_api="anthropic",
        model="mimo-v2.5-pro",
        review_model="mimo-v2.5-pro",
        api_key="tp-test-key",
    )
    defaults.update(overrides)
    return ModelProviderConfig(**defaults)


def _anthropic_response(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _openai_response(text: str) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


def _mock_anthropic_handler(expected_payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_anthropic_response(json.dumps(expected_payload)))
    return handler


def _mock_openai_handler(expected_payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_response(json.dumps(expected_payload)))
    return handler


class AnthropicClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = _anthropic_config()

    def test_build_messages_endpoint(self) -> None:
        client = AnthropicClient(self.config)
        self.assertEqual(client._build_messages_endpoint(), "https://token-plan-cn.xiaomimimo.com/anthropic/v1/messages")

    def test_build_messages_endpoint_with_v1_suffix(self) -> None:
        config = _anthropic_config(base_url="https://example.com/v1")
        client = AnthropicClient(config)
        self.assertEqual(client._build_messages_endpoint(), "https://example.com/v1/messages")

    def test_create_json_response_uses_x_api_key_header(self) -> None:
        seen_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_headers.update(dict(request.headers))
            return httpx.Response(200, json=_anthropic_response('{"ok": true}'))

        client = AnthropicClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))
        client.create_json_response(
            model="mimo-v2.5-pro",
            system_prompt="Return JSON.",
            user_payload={"test": True},
            schema_name="test_schema",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        )
        self.assertEqual(seen_headers.get("x-api-key"), "tp-test-key")
        self.assertNotIn("authorization", seen_headers)

    def test_create_json_response_sends_system_as_top_level(self) -> None:
        seen_body: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_body.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json=_anthropic_response('{"ok": true}'))

        client = AnthropicClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))
        client.create_json_response(
            model="mimo-v2.5-pro",
            system_prompt="You are a planner.",
            user_payload={"request": "open QQ"},
            schema_name="planner",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        )
        self.assertIn("system", seen_body)
        self.assertIn("You are a planner.", seen_body["system"])
        self.assertIn("messages", seen_body)
        self.assertEqual(seen_body["messages"][0]["role"], "user")
        self.assertEqual(seen_body["max_tokens"], 4096)
        self.assertNotIn("input", seen_body)

    def test_create_json_response_parses_json_output(self) -> None:
        expected = {"approved": True, "risk_level": "low"}
        handler = _mock_anthropic_handler(expected)
        client = AnthropicClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))

        result = client.create_json_response(
            model="mimo-v2.5-pro",
            system_prompt="Return JSON.",
            user_payload={},
            schema_name="test",
            schema={},
        )
        self.assertEqual(result, expected)

    def test_create_json_response_handles_markdown_fenced_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_anthropic_response('```json\n{"ok": true}\n```'))

        client = AnthropicClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))
        result = client.create_json_response(
            model="mimo-v2.5-pro",
            system_prompt="Return JSON.",
            user_payload={},
            schema_name="test",
            schema={},
        )
        self.assertEqual(result, {"ok": True})

    def test_create_json_response_retries_on_502(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(502, request=request, text="bad gateway")
            return httpx.Response(200, json=_anthropic_response('{"ok": true}'))

        client = AnthropicClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=2,
            retry_backoff_seconds=0,
        )
        result = client.create_json_response(
            model="mimo-v2.5-pro",
            system_prompt="Return JSON.",
            user_payload={},
            schema_name="retry_test",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, 3)

    def test_create_json_response_raises_on_exhausted_retries(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated", request=request)

        client = AnthropicClient(
            self.config,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            max_retries=1,
            retry_backoff_seconds=0,
        )
        with self.assertRaises(ProviderTransportError):
            client.create_json_response(
                model="mimo-v2.5-pro",
                system_prompt="Return JSON.",
                user_payload={},
                schema_name="fail_test",
                schema={},
            )

    def test_create_json_response_raises_on_non_json_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_anthropic_response("not json at all"))

        client = AnthropicClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))
        with self.assertRaises(ProviderResponseError):
            client.create_json_response(
                model="mimo-v2.5-pro",
                system_prompt="Return JSON.",
                user_payload={},
                schema_name="bad_json",
                schema={},
            )

    def test_create_json_response_includes_trace_id_header(self) -> None:
        seen_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen_headers.update(dict(request.headers))
            return httpx.Response(200, json=_anthropic_response('{"ok": true}'))

        client = AnthropicClient(self.config, client=httpx.Client(transport=httpx.MockTransport(handler)))
        client.create_json_response(
            model="mimo-v2.5-pro",
            system_prompt="Return JSON.",
            user_payload={},
            schema_name="test",
            schema={},
            trace_id="abc-123",
        )
        self.assertEqual(seen_headers.get("x-client-request-id"), "abc-123")


class ProviderFactoryTests(unittest.TestCase):
    def test_create_client_returns_openai_for_responses(self) -> None:
        config = _openai_config()
        client = create_client(config)
        self.assertIsInstance(client, OpenAIResponsesClient)

    def test_create_client_returns_anthropic_for_anthropic(self) -> None:
        config = _anthropic_config()
        client = create_client(config)
        self.assertIsInstance(client, AnthropicClient)

    def test_create_client_protocol_compatibility(self) -> None:
        for config in [_openai_config(), _anthropic_config()]:
            with self.subTest(wire_api=config.wire_api):
                client = create_client(config)
                self.assertTrue(hasattr(client, "create_json_response"))
                self.assertTrue(hasattr(client, "config"))

    def test_auto_detect_builds_correct_endpoints(self) -> None:
        """Verify the endpoint URL construction used by auto_detect."""
        from desktop_assistant.adapters.provider_factory import _build_openai_endpoint, _build_anthropic_endpoint

        self.assertEqual(_build_openai_endpoint("https://api.openai.com"), "https://api.openai.com/v1/responses")
        self.assertEqual(_build_openai_endpoint("https://api.openai.com/v1"), "https://api.openai.com/v1/responses")
        self.assertEqual(_build_anthropic_endpoint("https://example.com/anthropic"), "https://example.com/anthropic/v1/messages")
        self.assertEqual(_build_anthropic_endpoint("https://example.com/v1"), "https://example.com/v1/messages")


class LLMClientProtocolTests(unittest.TestCase):
    """Verify both clients satisfy the LLMClient protocol."""

    def test_openai_client_is_protocol_compatible(self) -> None:
        config = _openai_config()
        client = OpenAIResponsesClient(config)
        # Protocol check — just verify the method exists with right signature
        self.assertTrue(callable(getattr(client, "create_json_response", None)))

    def test_anthropic_client_is_protocol_compatible(self) -> None:
        config = _anthropic_config()
        client = AnthropicClient(config)
        self.assertTrue(callable(getattr(client, "create_json_response", None)))

    def test_both_clients_produce_same_output_for_same_input(self) -> None:
        expected = {"status": "ok", "items": [1, 2, 3]}

        openai_client = OpenAIResponsesClient(
            _openai_config(),
            client=httpx.Client(transport=httpx.MockTransport(_mock_openai_handler(expected))),
        )
        anthropic_client = AnthropicClient(
            _anthropic_config(),
            client=httpx.Client(transport=httpx.MockTransport(_mock_anthropic_handler(expected))),
        )

        schema = {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]}
        for client in (openai_client, anthropic_client):
            with self.subTest(type=type(client).__name__):
                result = client.create_json_response(
                    model="test",
                    system_prompt="Return JSON.",
                    user_payload={"x": 1},
                    schema_name="test",
                    schema=schema,
                )
                self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
