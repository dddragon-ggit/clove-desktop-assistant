from __future__ import annotations

import unittest

import httpx

from desktop_assistant.adapters.web_query import AnswerQueryHandler
from desktop_assistant.models import ActionStep, ActionType, ExecutionStatus, RiskLevel


def action(target: str) -> ActionStep:
    return ActionStep(
        action_type=ActionType.ANSWER_QUERY,
        target=target,
        risk_level=RiskLevel.LOW,
    )


class AnswerQueryHandlerTests(unittest.TestCase):
    def test_empty_query_returns_clear_diagnosis(self) -> None:
        handler = AnswerQueryHandler(client=httpx.Client(transport=httpx.MockTransport(lambda request: None)))

        result = handler.execute(action(" "), step_index=0, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "QUERY_EMPTY")

    def test_weather_query_uses_weather_endpoint(self) -> None:
        def responder(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "wttr.in")
            return httpx.Response(
                200,
                json={
                    "current_condition": [
                        {
                            "temp_C": "20",
                            "FeelsLikeC": "19",
                            "humidity": "40",
                            "windspeedKmph": "8",
                            "lang_zh": [{"value": "晴"}],
                        }
                    ],
                    "weather": [{"maxtempC": "25", "mintempC": "12"}],
                },
            )

        handler = AnswerQueryHandler(client=httpx.Client(transport=httpx.MockTransport(responder)))

        result = handler.execute(action("查询今天西安天气"), step_index=1, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertIn("西安今日天气", result.message)
        self.assertIn("晴", result.message)
        self.assertIn("Source: https://wttr.in/", result.message)
        self.assertEqual(result.metadata["strategy"], "weather_endpoint")
        self.assertEqual(result.metadata["confidence"], "high")
        self.assertEqual(result.metadata["source_count"], 1)
        self.assertEqual(result.metadata["verification_status"], "structured_source")
        self.assertIn("confidence_reason", result.metadata)
        self.assertEqual(result.metadata["attempted_sources"], ["wttr.in"])
        self.assertIn("checked_at", result.metadata)

    def test_duckduckgo_instant_answer_is_returned(self) -> None:
        def responder(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "Answer": "Python is a programming language.",
                    "AbstractURL": "https://www.python.org/",
                },
            )

        handler = AnswerQueryHandler(client=httpx.Client(transport=httpx.MockTransport(responder)))

        result = handler.execute(action("Python language"), step_index=0, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertIn("Python is a programming language.", result.message)
        self.assertIn("https://www.python.org/", result.message)
        self.assertEqual(result.metadata["strategy"], "duckduckgo_instant_answer")
        self.assertEqual(result.metadata["confidence"], "medium")
        self.assertEqual(result.metadata["sources"], ["https://www.python.org/"])
        self.assertEqual(result.metadata["verification_status"], "single_direct_source")
        self.assertIn("duckduckgo_instant", result.metadata["attempted_sources"])

    def test_html_snippets_are_used_when_instant_answer_is_empty(self) -> None:
        def responder(request: httpx.Request) -> httpx.Response:
            if request.url.host == "api.duckduckgo.com":
                return httpx.Response(200, json={})
            return httpx.Response(
                200,
                text="""
                <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">Example</a>
                <a class="result__snippet">A useful concise snippet.</a>
                """,
            )

        handler = AnswerQueryHandler(client=httpx.Client(transport=httpx.MockTransport(responder)))

        result = handler.execute(action("example lookup"), step_index=0, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertIn("A useful concise snippet.", result.message)
        self.assertIn("https://example.com", result.message)
        self.assertEqual(result.metadata["strategy"], "duckduckgo_html_snippets")
        self.assertEqual(result.metadata["confidence"], "low")
        self.assertEqual(result.metadata["sources"], ["https://example.com"])
        self.assertEqual(result.metadata["verification_status"], "single_snippet_source")
        self.assertIn("fallback_reason", result.metadata)
        self.assertIn("duckduckgo_html", result.metadata["attempted_sources"])

    def test_html_snippets_raise_confidence_when_multiple_sources_exist(self) -> None:
        def responder(request: httpx.Request) -> httpx.Response:
            if request.url.host == "api.duckduckgo.com":
                return httpx.Response(200, json={})
            return httpx.Response(
                200,
                text="""
                <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fone.example%2Fa">One</a>
                <a class="result__snippet">First source snippet.</a>
                <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftwo.example%2Fb">Two</a>
                <a class="result__snippet">Second source snippet.</a>
                """,
            )

        handler = AnswerQueryHandler(client=httpx.Client(transport=httpx.MockTransport(responder)))

        result = handler.execute(action("multi source lookup"), step_index=0, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.metadata["confidence"], "medium")
        self.assertEqual(result.metadata["verification_status"], "multi_source_summary")
        self.assertEqual(result.metadata["cross_check_source_count"], 2)

    def test_transport_errors_include_all_attempted_sources(self) -> None:
        def responder(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down", request=request)

        handler = AnswerQueryHandler(client=httpx.Client(transport=httpx.MockTransport(responder)))

        result = handler.execute(action("weather in nowhere"), step_index=0, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "WEB_QUERY_TRANSPORT_ERROR")
        self.assertIn("errors", result.diagnosis.details)
        self.assertGreaterEqual(len(result.diagnosis.details["errors"]), 1)
        self.assertEqual(result.metadata["strategy"], "transport_error")
        self.assertEqual(result.metadata["confidence"], "none")
        self.assertIn("fallback_url", result.metadata)
        self.assertIn("errors", result.metadata)
        self.assertGreaterEqual(result.metadata["attempted_source_count"], 1)

    def test_no_direct_answer_includes_fallback_metadata(self) -> None:
        def responder(request: httpx.Request) -> httpx.Response:
            if request.url.host == "api.duckduckgo.com":
                return httpx.Response(200, json={})
            return httpx.Response(200, text="<html></html>")

        handler = AnswerQueryHandler(client=httpx.Client(transport=httpx.MockTransport(responder)))

        result = handler.execute(action("obscure lookup"), step_index=0, trace_id="trace")

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNotNone(result.diagnosis)
        self.assertEqual(result.diagnosis.code, "WEB_QUERY_NO_DIRECT_ANSWER")
        self.assertEqual(result.metadata["strategy"], "no_direct_answer")
        self.assertEqual(result.metadata["confidence"], "none")
        self.assertEqual(result.metadata["source_count"], 0)
        self.assertIn("duckduckgo_instant", result.metadata["attempted_sources"])
        self.assertIn("duckduckgo_html", result.metadata["attempted_sources"])
        self.assertIn("https://www.baidu.com/s?wd=", result.metadata["fallback_url"])


if __name__ == "__main__":
    unittest.main()
