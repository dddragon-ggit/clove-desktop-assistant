from __future__ import annotations

from .view_models import WindowStateSummary


def summarize_window_metadata(metadata: dict) -> list[WindowStateSummary]:
    windows = metadata.get("windows") if isinstance(metadata, dict) else None
    foreground = metadata.get("foreground_window") if isinstance(metadata, dict) else None
    foreground_hwnd = _safe_int(foreground.get("hwnd")) if isinstance(foreground, dict) else None
    summaries: list[WindowStateSummary] = []
    if not isinstance(windows, list):
        return summaries

    for raw in windows:
        if not isinstance(raw, dict):
            continue
        hwnd = _safe_int(raw.get("hwnd"))
        if hwnd is None:
            continue
        summaries.append(
            WindowStateSummary(
                hwnd=hwnd,
                title=str(raw.get("title") or ""),
                process_id=_safe_int(raw.get("process_id")) or 0,
                executable_path=str(raw.get("executable_path") or ""),
                is_minimized=bool(raw.get("is_minimized")),
                is_maximized=bool(raw.get("is_maximized")),
                is_foreground=foreground_hwnd == hwnd,
            )
        )
    return summaries


def window_state_label(summary: WindowStateSummary) -> str:
    state = "已最小化" if summary.is_minimized else "已最大化" if summary.is_maximized else "普通"
    if summary.is_foreground:
        return f"前台，{state}"
    return state


def window_row_values(summary: WindowStateSummary) -> list[str]:
    return [
        str(summary.hwnd),
        summary.title or "-",
        str(summary.process_id),
        window_state_label(summary),
        summary.executable_path or "-",
    ]


def window_detail_to_plain_text(summary: WindowStateSummary) -> str:
    return "\n".join(
        [
            f"窗口：{summary.title or '-'}",
            f"句柄：{summary.hwnd}",
            f"进程 ID：{summary.process_id}",
            f"状态：{window_state_label(summary)}",
            f"程序位置：{summary.executable_path or '-'}",
        ]
    )


def _safe_int(value) -> int | None:  # noqa: ANN001 - accepts raw JSON-ish metadata
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
