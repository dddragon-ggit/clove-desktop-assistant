from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters.fake import FakeContextProvider, FakeExecutor, FakePlanner, FakeReviewer
from .adapters.openai_responses import OpenAIResponsesClient, ProviderResponseError, RealPlanner, RealReviewer
from .adapters.windows_executor import WindowsExecutor
from .action_trust import ActionTrustStore
from .capability.store import CapabilityStore
from .config import ProviderConfigStore
from .core.orchestrator import WorkflowOrchestrator
from .core.policy import PolicyEngine
from .models import RunMode, WorkflowRequest
from .storage.in_memory import InMemoryStorage
from .storage.sqlite import SQLiteStorage, default_database_path


def build_orchestrator(
    storage_backend: str = "sqlite",
    db_path: str | None = None,
    ai_backend: str = "fake",
    provider_config_path: str | None = None,
) -> WorkflowOrchestrator:
    if storage_backend == "memory":
        storage = InMemoryStorage()
    else:
        storage = SQLiteStorage(db_path=db_path)

    capability_store = CapabilityStore()
    capability_registry = capability_store.ensure(available_handler_names=WindowsExecutor.available_handler_names())
    try:
        trusted_action_keys = ActionTrustStore().trusted_keys()
    except Exception:  # noqa: BLE001 - trust store should not block planning
        trusted_action_keys = set()
    planner = FakePlanner()
    reviewer = FakeReviewer()
    provider_info: dict[str, str] | None = None

    if ai_backend == "real":
        store = ProviderConfigStore(path=provider_config_path)
        config = store.config_from_env() or store.load_or_raise()
        provider_info = {
            "provider_name": config.provider_name,
            "base_url": config.base_url,
            "model": config.model,
            "review_model": config.review_model,
            "reasoning_effort": config.model_reasoning_effort,
            "api_key_masked": config.masked_api_key,
            "config_path": str(store.path),
            "loaded_from": "env" if store.config_from_env() is not None else "file",
        }
        client = OpenAIResponsesClient(config)
        planner = RealPlanner(client, capability_registry=capability_registry)
        reviewer = RealReviewer(client, capability_registry=capability_registry)

    return WorkflowOrchestrator(
        planner=planner,
        reviewer=reviewer,
        executor=FakeExecutor(),
        context_provider=FakeContextProvider(),
        storage=storage,
        policy_engine=PolicyEngine(
            capability_registry=capability_registry,
            trusted_action_keys=trusted_action_keys,
        ),
        ai_backend=ai_backend,
        provider_config_path=provider_config_path,
    ), provider_info


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the desktop assistant fake workflow.")
    parser.add_argument("--request", default="开始做周报", help="Natural language request.")
    parser.add_argument(
        "--mode",
        default=RunMode.DRY_RUN.value,
        choices=[mode.value for mode in RunMode],
        help="Execution mode.",
    )
    parser.add_argument("--step", type=int, default=0, help="Step index for step-by-step mode.")
    parser.add_argument(
        "--storage",
        default="sqlite",
        choices=["sqlite", "memory"],
        help="Storage backend.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional SQLite database path. Defaults to runtime/data/desktop_assistant.db.",
    )
    parser.add_argument(
        "--ai-backend",
        default="fake",
        choices=["fake", "real"],
        help="Planner/reviewer backend.",
    )
    parser.add_argument(
        "--provider-config-path",
        default=None,
        help="Optional provider config JSON path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    orchestrator, provider_info = build_orchestrator(
        storage_backend=args.storage,
        db_path=args.db_path,
        ai_backend=args.ai_backend,
        provider_config_path=args.provider_config_path,
    )
    request = WorkflowRequest(
        user_request=args.request,
        run_mode=RunMode(args.mode),
        current_step=args.step,
    )
    output = {
        "storage_backend": args.storage,
        "ai_backend": args.ai_backend,
        "provider_config": provider_info,
        "database_path": str(Path(args.db_path) if args.db_path else default_database_path()),
    }
    try:
        trace = orchestrator.run(request)
        output["trace"] = trace.model_dump(mode="json")
    except ProviderResponseError as exc:
        output["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
