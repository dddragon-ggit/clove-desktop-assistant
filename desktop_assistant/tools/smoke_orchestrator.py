from __future__ import annotations

from typing import Any

from ..adapters.fake import FakeContextProvider, FakeExecutor, FakePlanner, FakeReviewer
from ..adapters.openai_responses import RealPlanner, RealReviewer
from ..adapters.windows_executor import WindowsExecutor
from ..capability.store import CapabilityStore
from ..config import ProviderConfigStore
from ..core.orchestrator import WorkflowOrchestrator
from ..core.policy import PolicyEngine
from ..storage.in_memory import InMemoryStorage
from .smoke_client import CountingOpenAIResponsesClient


def build_smoke_orchestrator(
    *,
    ai_backend: str,
    provider_config_path: str | None,
    timeout: float,
    max_retries: int,
    retry_backoff_seconds: float,
) -> tuple[WorkflowOrchestrator, dict[str, Any] | None, CountingOpenAIResponsesClient | None]:
    planner = FakePlanner()
    reviewer = FakeReviewer()
    capability_registry = CapabilityStore().ensure(available_handler_names=WindowsExecutor.available_handler_names())
    client: CountingOpenAIResponsesClient | None = None
    provider_info: dict[str, Any] | None = None

    if ai_backend == "real":
        store = ProviderConfigStore(path=provider_config_path)
        env_config = store.config_from_env()
        config = env_config or store.load_or_raise()
        provider_info = {
            "provider_name": config.provider_name,
            "base_url": config.base_url,
            "wire_api": config.wire_api,
            "model": config.model,
            "review_model": config.review_model,
            "reasoning_effort": config.model_reasoning_effort,
            "disable_response_storage": config.disable_response_storage,
            "api_key_masked": config.masked_api_key,
            "config_path": str(store.path),
            "loaded_from": "env" if env_config is not None else "file",
            "timeout": timeout,
            "max_retries": max_retries,
            "retry_backoff_seconds": retry_backoff_seconds,
        }
        client = CountingOpenAIResponsesClient(
            config,
            timeout=timeout,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        planner = RealPlanner(client, capability_registry=capability_registry)
        reviewer = RealReviewer(client, capability_registry=capability_registry)

    orchestrator = WorkflowOrchestrator(
        planner=planner,
        reviewer=reviewer,
        executor=FakeExecutor(),
        context_provider=FakeContextProvider(),
        storage=InMemoryStorage(),
        policy_engine=PolicyEngine(capability_registry=capability_registry),
    )
    return orchestrator, provider_info, client
