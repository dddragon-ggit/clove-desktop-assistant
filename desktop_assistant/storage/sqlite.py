from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from ..models import DebugRunRecord, RecentTraceRecord, WorkflowStatus, WorkflowTrace


def default_database_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd() / "runtime"
    return root / "data" / "desktop_assistant.db"


def connect_sqlite(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@dataclass(frozen=True)
class SqliteMigration:
    version: int
    name: str
    description: str
    apply: Callable[[sqlite3.Connection], None]


def ensure_sqlite_schema(connection: sqlite3.Connection) -> None:
    with connection:
        _ensure_migration_table(connection)
        current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        _backfill_migration_history(connection, current_version)
        for migration in _SQLITE_MIGRATIONS:
            if current_version >= migration.version:
                continue
            migration.apply(connection)
            connection.execute(f"PRAGMA user_version = {migration.version}")
            _record_migration(connection, migration)
            current_version = migration.version


def list_sqlite_migrations(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    _ensure_migration_table(connection)
    return connection.execute(
        """
        SELECT version, name, description, applied_at
        FROM schema_migrations
        ORDER BY version ASC
        """
    ).fetchall()


def get_storage_metadata(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute(
        "SELECT value FROM storage_metadata WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row is not None else None


def set_storage_metadata(connection: sqlite3.Connection, key: str, value: str) -> None:
    timestamp = datetime.now(UTC).isoformat()
    connection.execute(
        """
        INSERT INTO storage_metadata (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, timestamp),
    )


class SQLiteStorage:
    """SQLite-backed storage for traces and debug runs."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_database_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_trace(self, trace: WorkflowTrace) -> None:
        payload = json.dumps(trace.model_dump(mode="json"), ensure_ascii=False)
        timestamp = self._timestamp()

        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO workflow_traces (
                        trace_id,
                        status,
                        trace_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(trace_id) DO UPDATE SET
                        status = excluded.status,
                        trace_json = excluded.trace_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        trace.trace_id,
                        trace.status.value,
                        payload,
                        timestamp,
                        timestamp,
                    ),
                )

    def get_trace(self, trace_id: str) -> WorkflowTrace:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT trace_json FROM workflow_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()

        if row is None:
            raise KeyError(f"Unknown trace_id: {trace_id}")

        return WorkflowTrace.model_validate(json.loads(row["trace_json"]))

    def list_recent_traces(self, limit: int = 10) -> list[RecentTraceRecord]:
        safe_limit = max(1, min(limit, 100))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT trace_id, status, trace_json, created_at, updated_at
                FROM workflow_traces
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        return [
            RecentTraceRecord(
                trace_id=row["trace_id"],
                status=WorkflowStatus(row["status"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                trace=WorkflowTrace.model_validate(json.loads(row["trace_json"])),
            )
            for row in rows
        ]

    def save_debug_run(self, debug_run: DebugRunRecord) -> None:
        payload = json.dumps(debug_run.model_dump(mode="json"), ensure_ascii=False)
        timestamp = self._timestamp()

        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO debug_runs (
                        id,
                        trace_id,
                        run_mode,
                        status,
                        debug_run_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        trace_id = excluded.trace_id,
                        run_mode = excluded.run_mode,
                        status = excluded.status,
                        debug_run_json = excluded.debug_run_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        debug_run.id,
                        debug_run.trace_id,
                        debug_run.run_mode.value,
                        debug_run.status.value,
                        payload,
                        timestamp,
                        timestamp,
                    ),
                )

    def list_debug_runs(self, trace_id: str | None = None) -> list[DebugRunRecord]:
        query = "SELECT debug_run_json, created_at, updated_at FROM debug_runs"
        parameters: tuple[str, ...] = ()
        if trace_id is not None:
            query += " WHERE trace_id = ?"
            parameters = (trace_id,)
        query += " ORDER BY created_at ASC"

        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()

        debug_runs: list[DebugRunRecord] = []
        for row in rows:
            debug_run = DebugRunRecord.model_validate(json.loads(row["debug_run_json"]))
            debug_run.created_at = row["created_at"]
            debug_run.updated_at = row["updated_at"]
            debug_runs.append(debug_run)
        return debug_runs

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            ensure_sqlite_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.db_path)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()


def _migration_1_workflow_storage(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_traces (
            trace_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            trace_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS debug_runs (
            id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            run_mode TEXT NOT NULL,
            status TEXT NOT NULL,
            debug_run_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _migration_2_todo_storage(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS todo_items (
            item_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            priority_rank INTEGER NOT NULL,
            important INTEGER NOT NULL,
            next_time TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            todo_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_todo_items_status_next_time ON todo_items(status, next_time, updated_at)"
    )


def _migration_3_workspace_drafts(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_drafts (
            suggestion_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            has_actions INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            draft_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_drafts_status_updated_at ON workspace_drafts(status, updated_at)"
    )


def _migration_4_workflow_recipes(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_recipes (
            recipe_id TEXT PRIMARY KEY,
            scenario TEXT NOT NULL,
            name TEXT NOT NULL,
            user_goal TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            recipe_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_recipes_scenario_updated_at ON workflow_recipes(scenario, updated_at)"
    )


def _migration_5_storage_metadata(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS storage_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def _record_migration(connection: sqlite3.Connection, migration: SqliteMigration) -> None:
    timestamp = datetime.now(UTC).isoformat()
    connection.execute(
        """
        INSERT INTO schema_migrations (version, name, description, applied_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(version) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            applied_at = excluded.applied_at
        """,
        (migration.version, migration.name, migration.description, timestamp),
    )


def _backfill_migration_history(connection: sqlite3.Connection, current_version: int) -> None:
    if current_version <= 0:
        return
    existing = {
        int(row["version"])
        for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for migration in _SQLITE_MIGRATIONS:
        if migration.version > current_version or migration.version in existing:
            continue
        _record_migration(connection, migration)


_SQLITE_MIGRATIONS = [
    SqliteMigration(
        version=1,
        name="workflow_storage",
        description="Create workflow traces and debug runs tables.",
        apply=_migration_1_workflow_storage,
    ),
    SqliteMigration(
        version=2,
        name="todo_storage",
        description="Create todo_items table and indexes.",
        apply=_migration_2_todo_storage,
    ),
    SqliteMigration(
        version=3,
        name="workspace_drafts",
        description="Create workspace_drafts table and indexes.",
        apply=_migration_3_workspace_drafts,
    ),
    SqliteMigration(
        version=4,
        name="workflow_recipes",
        description="Create workflow_recipes table and indexes.",
        apply=_migration_4_workflow_recipes,
    ),
    SqliteMigration(
        version=5,
        name="storage_metadata",
        description="Create key/value metadata for one-time storage migrations.",
        apply=_migration_5_storage_metadata,
    ),
]
