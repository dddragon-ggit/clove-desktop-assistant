from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ..config import ModelProviderConfig


class ProviderResponseError(RuntimeError):
    """Raised when the provider returns an unusable response."""


class ProviderTransportError(ProviderResponseError):
    """Raised when the provider cannot be reached reliably."""


class OpenAIResponsesClient:
    """Minimal client for OpenAI-compatible Responses API providers."""

    RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        config: ModelProviderConfig,
        *,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self.config = config
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)

    def create_json_response(
        self,
        *,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str,
        schema: dict[str, Any],
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        endpoint = self._build_responses_endpoint()
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if trace_id:
            headers["X-Client-Request-Id"] = trace_id

        body: dict[str, Any] = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "reasoning": {"effort": self.config.model_reasoning_effort},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        if self.config.disable_response_storage:
            body["store"] = False

        try:
            return self._request_json_payload(
                endpoint=endpoint,
                headers=headers,
                body=body,
                operation=f"{schema_name} structured request",
            )
        except ProviderTransportError:
            raise
        except ProviderResponseError:
            return self._fallback_json_prompt(
                endpoint=endpoint,
                headers=headers,
                model=model,
                system_prompt=system_prompt,
                user_payload=user_payload,
                schema=schema,
            )

    def _fallback_json_prompt(
        self,
        *,
        endpoint: str,
        headers: dict[str, str],
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        fallback_prompt = "\n\n".join(
            [
                system_prompt,
                "Return valid JSON only. Do not include markdown fences or extra commentary.",
                f"Target schema: {json.dumps(schema, ensure_ascii=False)}",
                f"User payload: {json.dumps(user_payload, ensure_ascii=False)}",
            ]
        )
        body: dict[str, Any] = {
            "model": model,
            "input": fallback_prompt,
            "reasoning": {"effort": self.config.model_reasoning_effort},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "fallback_json",
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        if self.config.disable_response_storage:
            body["store"] = False

        return self._request_json_payload(
            endpoint=endpoint,
            headers=headers,
            body=body,
            operation="fallback JSON prompt",
        )

    def _request_json_payload(
        self,
        *,
        endpoint: str,
        headers: dict[str, str],
        body: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        payload = self._post_with_retries(
            endpoint=endpoint,
            headers=headers,
            body=body,
            operation=operation,
        )
        text = self._extract_output_text(payload)
        return self._parse_json_output(text, operation)

    def _post_with_retries(
        self,
        *,
        endpoint: str,
        headers: dict[str, str],
        body: dict[str, Any],
        operation: str,
    ) -> dict[str, Any]:
        attempts = self.max_retries + 1
        for attempt_index in range(attempts):
            try:
                response = self._client.post(endpoint, headers=headers, json=body)
                if self._should_retry_status(response.status_code) and attempt_index < self.max_retries:
                    self._sleep_before_retry(attempt_index)
                    continue

                response.raise_for_status()
                return response.json()
            except httpx.TransportError as exc:
                if attempt_index < self.max_retries:
                    self._sleep_before_retry(attempt_index)
                    continue
                raise ProviderTransportError(
                    f"{operation} failed after {attempts} attempts: {type(exc).__name__}: {exc}"
                ) from exc
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                body_preview = exc.response.text[:300].replace("\n", " ")
                raise ProviderResponseError(
                    f"{operation} returned HTTP {status_code} after {attempt_index + 1} attempt(s): {body_preview}"
                ) from exc
            except json.JSONDecodeError as exc:
                raise ProviderResponseError(f"{operation} returned invalid provider JSON.") from exc

        raise ProviderResponseError(f"{operation} failed after {attempts} attempts.")

    @classmethod
    def _should_retry_status(cls, status_code: int) -> bool:
        return status_code in cls.RETRY_STATUS_CODES

    def _sleep_before_retry(self, attempt_index: int) -> None:
        if self.retry_backoff_seconds <= 0:
            return
        time.sleep(self.retry_backoff_seconds * (2**attempt_index))

    def _build_responses_endpoint(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/responses"
        return f"{base}/v1/responses"

    @staticmethod
    def _extract_output_text(payload: dict[str, Any]) -> str:
        if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
            return payload["output_text"]

        output_items = payload.get("output", [])
        for item in output_items:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
                if content.get("type") == "refusal" and isinstance(content.get("refusal"), str):
                    raise ProviderResponseError(f"Model refused the request: {content['refusal']}")

        raise ProviderResponseError("Could not extract output text from provider response.")

    @staticmethod
    def _parse_json_output(text: str, operation: str) -> dict[str, Any]:
        candidates = [text.strip()]
        fenced = _strip_markdown_json_fence(text)
        if fenced not in candidates:
            candidates.append(fenced)
        bounded = _extract_json_object_text(text)
        if bounded and bounded not in candidates:
            candidates.append(bounded)

        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
            raise ProviderResponseError(f"{operation} returned JSON, but it was not an object.")

        raise ProviderResponseError(f"{operation} did not return valid JSON output.")


def _strip_markdown_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip().startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _extract_json_object_text(text: str) -> str | None:
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return stripped[start : end + 1]
