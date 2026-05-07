from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..activity import ActivitySnapshot


def default_activity_days_dir(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "activity_days"


class DailyActivityJournal:
    """Append metadata-only activity summaries to date-named Markdown files."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else default_activity_days_dir()

    def append_snapshot(self, snapshot: ActivitySnapshot) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for_date(_date_label(snapshot.captured_at))
        line = _snapshot_line(snapshot)
        if _last_activity_line(path) == line:
            return path
        if not path.exists():
            path.write_text(f"# {path.stem} activity\n\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return path

    def prune_old(self, *, keep_days: int = 14, now: datetime | None = None) -> list[Path]:
        self.directory.mkdir(parents=True, exist_ok=True)
        cutoff = (now or datetime.now(UTC)).date() - timedelta(days=max(0, keep_days - 1))
        deleted: list[Path] = []
        for path in self.directory.glob("*.md"):
            try:
                date_value = datetime.strptime(path.stem, "%Y-%m-%d").date()
            except ValueError:
                continue
            if date_value < cutoff:
                path.unlink(missing_ok=True)
                deleted.append(path)
        return deleted

    def path_for_date(self, date_label: str) -> Path:
        return self.directory / f"{date_label}.md"


def _date_label(captured_at: str) -> str:
    try:
        return datetime.fromisoformat(captured_at.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return datetime.now(UTC).date().isoformat()


def _snapshot_line(snapshot: ActivitySnapshot) -> str:
    time_label = _time_label(snapshot.captured_at)
    app = snapshot.active_app.name if snapshot.active_app else "(unknown app)"
    project = snapshot.active_project.name if snapshot.active_project else ""
    file_name = snapshot.active_file.name if snapshot.active_file else ""
    parts = [f"- {time_label}", f"app={app}"]
    if project:
        parts.append(f"project={project}")
    if file_name:
        parts.append(f"file={file_name}")
    if snapshot.active_window and snapshot.active_window.title:
        parts.append(f"title={snapshot.active_window.title}")
    return " | ".join(parts)


def _time_label(captured_at: str) -> str:
    try:
        return datetime.fromisoformat(captured_at.replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        return datetime.now(UTC).strftime("%H:%M")


def _last_activity_line(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            last_match: str | None = None
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("- "):
                    last_match = stripped
            return last_match
    except OSError:
        return None
