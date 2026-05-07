from __future__ import annotations

import json
import os
import time
import tempfile
from pathlib import Path
from typing import Any


def write_text_atomic(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=encoding,
            dir=target.parent,
            prefix=f".{target.stem}-",
            suffix=f"{target.suffix}.tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        last_error: OSError | None = None
        for _attempt in range(6):
            try:
                os.replace(temp_path, target)
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.05)
        if last_error is not None:
            raise last_error
    except Exception:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def write_json_atomic(
    path: str | Path,
    payload: Any,
    *,
    encoding: str = "utf-8",
    ensure_ascii: bool = False,
    indent: int = 2,
) -> None:
    text = json.dumps(payload, ensure_ascii=ensure_ascii, indent=indent)
    write_text_atomic(path, text, encoding=encoding)


def quarantine_corrupted_file(
    path: str | Path,
    *,
    suffix: str = ".corrupt",
    category: str,
    source: str,
    reason: str = "",
    record_event: bool = True,
) -> Path | None:
    target = Path(path)
    if not target.exists():
        return None
    quarantined = target.with_name(f"{target.name}{suffix}")
    counter = 1
    while quarantined.exists():
        quarantined = target.with_name(f"{target.name}{suffix}.{counter}")
        counter += 1
    os.replace(target, quarantined)
    if record_event:
        try:
            from .recovery_events import record_recovery_event

            record_recovery_event(
                source=source,
                category=category,
                path=target,
                quarantined_path=quarantined,
                reason=reason,
            )
        except Exception:
            pass
    return quarantined
