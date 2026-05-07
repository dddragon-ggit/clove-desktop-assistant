from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..adapters.windows_executor import WindowsExecutor
from ..capabilities import CapabilityRegistry
from ..capability.store import CapabilityStore
from ..protocols import StorageProtocol
from ..storage.recovery_events import RecoveryEventStore
from ..storage.sqlite import SQLiteStorage
from ..ui.view_model import CapabilitySummary, capability_label, summarize_capability_registry


def build_capability_debug_report(
    *,
    registry: CapabilityRegistry | None = None,
    store: CapabilityStore | None = None,
    storage: StorageProtocol | None = None,
    catalog_path: str | Path | None = None,
    available_handler_names: Iterable[str] | None = None,
    recent_limit: int = 50,
    recovery_store: RecoveryEventStore | None = None,
    recovery_limit: int = 10,
) -> dict[str, Any]:
    """Build a read-only diagnostics report for capability wiring and recent failures."""

    available = set(available_handler_names or WindowsExecutor.available_handler_names())
    if store is not None:
        capability_store = store
    elif catalog_path is not None:
        capability_store = CapabilityStore(path=catalog_path)
    else:
        capability_store = CapabilityStore()
    catalog = str(capability_store.path)

    if registry is None:
        registry = capability_store.ensure(available_handler_names=available)

    storage_error = ""
    try:
        recent_traces = (storage or SQLiteStorage()).list_recent_traces(limit=recent_limit)
    except Exception as exc:  # noqa: BLE001 - diagnostics should survive corrupt or unavailable history
        recent_traces = []
        storage_error = f"{type(exc).__name__}: {exc}"

    summaries = summarize_capability_registry(
        registry,
        catalog_path=catalog,
        available_handler_names=available,
        recent_traces=recent_traces,
    )
    recovery_error = ""
    try:
        recovery_events = (recovery_store or RecoveryEventStore()).load()
    except Exception as exc:  # noqa: BLE001 - diagnostics should stay readable
        recovery_events = []
        recovery_error = f"{type(exc).__name__}: {exc}"
    recent_recovery_events = sorted(recovery_events, key=lambda item: item.created_at, reverse=True)[:recovery_limit]
    return _report_from_summaries(
        summaries,
        catalog_path=catalog,
        storage_error=storage_error,
        recent_recovery_events=recent_recovery_events,
        recovery_error=recovery_error,
    )


def format_capability_debug_report(report: dict[str, Any]) -> str:
    lines = [
        "Capability Debug Report",
        f"Catalog: {report.get('catalog_path') or '-'}",
        f"Total: {report.get('total', 0)}",
        f"Enabled: {report.get('enabled', 0)}",
        f"Disabled: {report.get('disabled', 0)}",
        f"Missing handlers: {report.get('missing_handlers', 0)}",
        f"Recent failures: {report.get('recent_failures', 0)}",
    ]
    if report.get("storage_error"):
        lines.append(f"Storage error: {report['storage_error']}")
    if report.get("recovery_error"):
        lines.append(f"Recovery error: {report['recovery_error']}")
    lines.append(f"Recovery events: {report.get('recovery_event_count', 0)}")
    lines.append("")
    lines.append("Capabilities")
    for item in report.get("capabilities", []):
        lines.append(
            "- "
            + f"{item['action_type']}: mode={item['execution_mode']} "
            + f"risk={item['default_risk']} handler={item['handler_name']} "
            + f"status={item['handler_status']} failures={item['recent_failure_count']}"
        )
        if item.get("recent_failure_code"):
            lines.append(
                "  "
                + f"last_failure={item['recent_failure_code']} "
                + f"trace={item.get('recent_failure_trace_id') or '-'} "
                + f"remedy={item.get('recent_failure_remedy') or '-'}"
            )
    if report.get("recent_recovery_events"):
        lines.append("")
        lines.append("Recent recovery events")
        for event in report["recent_recovery_events"]:
            lines.append(
                "- "
                + f"{event['created_at']} | {event['source']} | {event['category']} | "
                + f"{event['quarantined_path']}"
            )
    return "\n".join(lines)


def _report_from_summaries(
    summaries: list[CapabilitySummary],
    *,
    catalog_path: str,
    storage_error: str = "",
    recent_recovery_events: list | None = None,
    recovery_error: str = "",
) -> dict[str, Any]:
    enabled = [summary for summary in summaries if summary.enabled]
    disabled = [summary for summary in summaries if not summary.enabled]
    missing = [summary for summary in summaries if summary.enabled and summary.handler_status == "missing"]
    recent_failures = sum(summary.recent_failure_count for summary in summaries)
    return {
        "catalog_path": catalog_path,
        "total": len(summaries),
        "enabled": len(enabled),
        "disabled": len(disabled),
        "missing_handlers": len(missing),
        "recent_failures": recent_failures,
        "storage_error": storage_error,
        "recovery_error": recovery_error,
        "recovery_event_count": len(recent_recovery_events or []),
        "recent_recovery_events": [
            {
                "id": event.id,
                "created_at": event.created_at,
                "source": event.source,
                "category": event.category,
                "path": event.path,
                "quarantined_path": event.quarantined_path,
                "reason": event.reason,
            }
            for event in (recent_recovery_events or [])
        ],
        "capabilities": [
            {
                **summary.model_dump(mode="json"),
                "label": capability_label(summary),
            }
            for summary in summaries
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect capability handler wiring and recent failures.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument("--catalog", default=None, help="Optional capability catalog path.")
    parser.add_argument("--recent-limit", type=int, default=50, help="Number of recent traces to scan.")
    args = parser.parse_args(argv)

    report = build_capability_debug_report(catalog_path=args.catalog, recent_limit=args.recent_limit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_capability_debug_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
