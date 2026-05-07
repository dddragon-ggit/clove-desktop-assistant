from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from ..storage import quarantine_corrupted_file, write_json_atomic
from ..storage.sqlite import (
    connect_sqlite,
    default_database_path,
    ensure_sqlite_schema,
    get_storage_metadata,
    set_storage_metadata,
)
from .models import WorkspaceSuggestion


WORKSPACE_DRAFT_SCHEMA_VERSION = 1


class WorkspaceDraft(BaseModel):
    suggestion: WorkspaceSuggestion
    status: str = "pending"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


def default_workspace_draft_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "workspace_drafts.json"


def default_workspace_draft_database_path(base_dir: str | Path | None = None) -> Path:
    return default_database_path(base_dir)


class WorkspaceDraftStore:
    def __init__(self, path: str | Path | None = None) -> None:
        resolved = Path(path) if path is not None else default_workspace_draft_database_path()
        self.path = resolved
        self._use_sqlite = resolved.suffix.lower() == ".db" or path is None
        self._legacy_json_path = default_workspace_draft_path() if self._use_sqlite and path is None else None
        if self._use_sqlite:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)

    def load(self) -> list[WorkspaceDraft]:
        if self._use_sqlite:
            return self._load_sqlite()
        return self._load_json()

    def _load_json(self) -> list[WorkspaceDraft]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            quarantine_corrupted_file(
                self.path,
                source="workspace_draft_store",
                category="workspace_draft_store_corrupted",
                reason="Workspace draft JSON is unreadable.",
            )
            return []
        raw_drafts = payload.get("drafts") if isinstance(payload, dict) else []
        if not isinstance(raw_drafts, list):
            quarantine_corrupted_file(
                self.path,
                source="workspace_draft_store",
                category="workspace_draft_store_invalid",
                reason="Workspace drafts must be a list.",
            )
            return []
        try:
            return [WorkspaceDraft.model_validate(item) for item in raw_drafts if isinstance(item, dict)]
        except Exception:
            quarantine_corrupted_file(
                self.path,
                source="workspace_draft_store",
                category="workspace_draft_store_invalid",
                reason="Workspace draft items could not be validated.",
            )
            return []

    def save(self, drafts: list[WorkspaceDraft]) -> None:
        if self._use_sqlite:
            self._save_sqlite(drafts)
            return
        payload = {
            "schema_version": WORKSPACE_DRAFT_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "drafts": [draft.model_dump(mode="json") for draft in drafts],
        }
        write_json_atomic(self.path, payload)

    def upsert(self, suggestion: WorkspaceSuggestion, *, status: str | None = None) -> WorkspaceDraft:
        if self._use_sqlite:
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)
                self._maybe_import_legacy_json(connection)
                existing = self._get_sqlite(connection, suggestion.id)
                draft_status = status or (existing.status if existing is not None else "pending")
                draft = WorkspaceDraft(
                    suggestion=suggestion,
                    status=draft_status,
                    updated_at=datetime.now(UTC).isoformat(),
                )
                if existing is not None:
                    draft.created_at = existing.created_at
                self._upsert_sqlite(connection, draft)
                return draft
        drafts = self.load()
        now = datetime.now(UTC).isoformat()
        by_id = {item.suggestion.id: item for item in drafts}
        draft_status = status or (by_id[suggestion.id].status if suggestion.id in by_id else "pending")
        draft = WorkspaceDraft(suggestion=suggestion, status=draft_status, updated_at=now)
        if suggestion.id in by_id:
            draft.created_at = by_id[suggestion.id].created_at
        by_id[suggestion.id] = draft
        self.save(list(by_id.values()))
        return draft

    def latest_pending(self) -> WorkspaceSuggestion | None:
        if self._use_sqlite:
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)
                self._maybe_import_legacy_json(connection)
                row = connection.execute(
                    """
                    SELECT draft_json
                    FROM workspace_drafts
                    WHERE status = 'pending' AND has_actions = 1
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ).fetchone()
            if row is None:
                return None
            return WorkspaceDraft.model_validate(json.loads(row["draft_json"])).suggestion
        pending = [draft for draft in self.load() if draft.status == "pending" and draft.suggestion.has_actions()]
        if not pending:
            return None
        return max(pending, key=lambda draft: draft.updated_at).suggestion

    def get_pending(self, suggestion_id: str | None) -> WorkspaceSuggestion | None:
        if self._use_sqlite:
            if not suggestion_id:
                return None
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)
                self._maybe_import_legacy_json(connection)
                row = connection.execute(
                    """
                    SELECT draft_json
                    FROM workspace_drafts
                    WHERE suggestion_id = ? AND status = 'pending'
                    """,
                    (suggestion_id,),
                ).fetchone()
            if row is None:
                return None
            return WorkspaceDraft.model_validate(json.loads(row["draft_json"])).suggestion
        if not suggestion_id:
            return None
        for draft in self.load():
            if draft.status == "pending" and draft.suggestion.id == suggestion_id:
                return draft.suggestion
        return None

    def mark_status(self, suggestion_id: str, status: str) -> bool:
        if self._use_sqlite:
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)
                self._maybe_import_legacy_json(connection)
                existing = self._get_sqlite(connection, suggestion_id)
                if existing is None:
                    return False
                updated = existing.model_copy(update={"status": status, "updated_at": datetime.now(UTC).isoformat()})
                self._upsert_sqlite(connection, updated)
                return True
        changed = False
        drafts = []
        for draft in self.load():
            if draft.suggestion.id == suggestion_id:
                draft.status = status
                draft.updated_at = datetime.now(UTC).isoformat()
                changed = True
            drafts.append(draft)
        if changed:
            self.save(drafts)
        return changed

    def _load_sqlite(self) -> list[WorkspaceDraft]:
        with connect_sqlite(self.path) as connection:
            ensure_sqlite_schema(connection)
            self._maybe_import_legacy_json(connection)
            rows = connection.execute(
                "SELECT draft_json FROM workspace_drafts ORDER BY updated_at DESC"
            ).fetchall()
        return [WorkspaceDraft.model_validate(json.loads(row["draft_json"])) for row in rows]

    def _save_sqlite(self, drafts: list[WorkspaceDraft]) -> None:
        with connect_sqlite(self.path) as connection:
            ensure_sqlite_schema(connection)
            self._maybe_import_legacy_json(connection)
            with connection:
                connection.execute("DELETE FROM workspace_drafts")
                for draft in drafts:
                    self._upsert_sqlite(connection, draft)

    def _maybe_import_legacy_json(self, connection: sqlite3.Connection) -> None:
        if self._legacy_json_path is None or not self._legacy_json_path.exists():
            return
        if get_storage_metadata(connection, "workspace_drafts_legacy_json_imported") == "1":
            return
        row = connection.execute("SELECT COUNT(*) AS count FROM workspace_drafts").fetchone()
        if row is not None and int(row["count"] or 0) > 0:
            set_storage_metadata(connection, "workspace_drafts_legacy_json_imported", "1")
            return
        legacy_store = WorkspaceDraftStore(self._legacy_json_path)
        drafts = legacy_store.load()
        with connection:
            for draft in drafts:
                self._upsert_sqlite(connection, draft)
            set_storage_metadata(connection, "workspace_drafts_legacy_json_imported", "1")

    def _get_sqlite(self, connection: sqlite3.Connection, suggestion_id: str) -> WorkspaceDraft | None:
        row = connection.execute(
            "SELECT draft_json FROM workspace_drafts WHERE suggestion_id = ?",
            (suggestion_id,),
        ).fetchone()
        if row is None:
            return None
        return WorkspaceDraft.model_validate(json.loads(row["draft_json"]))

    def _upsert_sqlite(self, connection: sqlite3.Connection, draft: WorkspaceDraft) -> None:
        payload = json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)
        connection.execute(
            """
            INSERT INTO workspace_drafts (
                suggestion_id,
                status,
                has_actions,
                created_at,
                updated_at,
                draft_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(suggestion_id) DO UPDATE SET
                status = excluded.status,
                has_actions = excluded.has_actions,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                draft_json = excluded.draft_json
            """,
            (
                draft.suggestion.id,
                draft.status,
                1 if draft.suggestion.has_actions() else 0,
                draft.created_at,
                draft.updated_at,
                payload,
            ),
        )
