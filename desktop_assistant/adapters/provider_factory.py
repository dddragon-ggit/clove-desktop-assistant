from __future__ import annotations

import json
import logging
from typing import Any, Protocol

import httpx

from ..config import ModelProviderConfig, ProviderConfigStore
from .openai_client import OpenAIResponsesClient, ProviderResponseError, ProviderTransportError

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol matching both OpenAI and Anthropic clients."""

    config: ModelProviderConfig

    def create_json_response(
        self,
        *,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema_name: str,
        schema: dict[str, Any],
        trace_id: str | None = None,
    ) -> dict[str, Any]: ...


def create_client(config: ModelProviderConfig, **kwargs: Any) -> LLMClient:
    """Create the right client based on ``config.wire_api``."""
    if config.wire_api == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(config, **kwargs)
    return OpenAIResponsesClient(config, **kwargs)


def auto_detect_wire_api(
    config: ModelProviderConfig,
    *,
    timeout: float = 15.0,
) -> str:
    """Probe the provider and return ``"responses"`` or ``"anthropic"``.

    Tries a lightweight OpenAI Responses API call first.  If that fails with
    a transport or auth error consistent with a non-OpenAI endpoint, falls
    back to an Anthropic Messages API probe.

    Returns the wire_api string that should be persisted in config.
    """
    client = httpx.Client(timeout=timeout)

    # --- Probe OpenAI Responses API ---
    openai_endpoint = _build_openai_endpoint(config.base_url)
    openai_headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    openai_body = {
        "model": config.model,
        "input": [{"role": "user", "content": "hi"}],
        "text": {"format": {"type": "text"}},
    }
    try:
        resp = client.post(openai_endpoint, headers=openai_headers, json=openai_body)
        if resp.status_code < 400:
            logger.info("Auto-detected wire_api=responses")
            return "responses"
    except httpx.TransportError:
        pass

    # --- Probe Anthropic Messages API ---
    anthropic_endpoint = _build_anthropic_endpoint(config.base_url)
    anthropic_headers = {
        "x-api-key": config.api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    anthropic_body = {
        "model": config.model,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "hi"}],
    }
    try:
        resp = client.post(anthropic_endpoint, headers=anthropic_headers, json=anthropic_body)
        if resp.status_code < 400:
            logger.info("Auto-detected wire_api=anthropic")
            return "anthropic"
    except httpx.TransportError:
        pass

    # Default to responses if neither probe succeeded
    logger.warning("Could not auto-detect wire_api, defaulting to responses")
    return "responses"


def probe_provider(config: ModelProviderConfig, *, timeout: float = 15.0) -> dict[str, Any]:
    """Probe the provider and return status info.

    Returns a dict like:
        {"ok": True, "wire_api": "responses", "model": "gpt-4o"}
    or:
        {"ok": False, "wire_api": "anthropic", "error": "HTTP 401: ..."}
    """
    client = httpx.Client(timeout=timeout)
    results: dict[str, Any] = {}

    for wire_api in ("responses", "anthropic"):
        if wire_api == "responses":
            endpoint = _build_openai_endpoint(config.base_url)
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": config.model,
                "input": [{"role": "user", "content": "say ok"}],
                "text": {"format": {"type": "text"}},
            }
        else:
            endpoint = _build_anthropic_endpoint(config.base_url)
            headers = {
                "x-api-key": config.api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            }
            body = {
                "model": config.model,
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "say ok"}],
            }

        try:
            resp = client.post(endpoint, headers=headers, json=body)
            if resp.status_code < 400:
                return {"ok": True, "wire_api": wire_api, "status": resp.status_code}
            results[wire_api] = {"status": resp.status_code, "body": resp.text[:200]}
        except httpx.TransportError as exc:
            results[wire_api] = {"error": str(exc)}

    return {"ok": False, "details": results}


def _build_openai_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/responses"
    return f"{base}/v1/responses"


def _build_anthropic_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/v1/messages"
