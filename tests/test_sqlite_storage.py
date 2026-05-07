from __future__ import annotations

import unittest
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from desktop_assistant.adapters.fake import FakeContextProvider, FakeExecutor, FakePlanner, FakeReviewer
from desktop_assistant.core.orchestrator import WorkflowOrchestrator
from desktop_assistant.core.policy import PolicyEngine
from desktop_assistant.models import RunMode, WorkflowRequest, WorkflowStatus
from desktop_assistant.storage.sqlite import SQLiteStorage, connect_sqlite, ensure_sqlite_schema, list_sqlite_migrations


def build_orchestrator(db_path: Path) -> WorkflowOrchestrator:
    return WorkflowOrchestrator(
        planner=FakePlanner(),
        reviewer=FakeReviewer(),
        executor=FakeExecutor(),
        context_provider=FakeContextProvider(),
        storage=SQLiteStorage(db_path=db_path),
        policy_engine=PolicyEngine(),
    )


class SQLiteStorageTests(unittest.TestCase):
    @contextmanager
    def _workspace_db_path(self):
        base_dir = Path.cwd() / "runtime" / "test_db"
        base_dir.mkdir(parents=True, exist_ok=True)
        db_path = base_dir / f"{uuid4().hex}.db"
        try:
            if db_path.exists():
                db_path.unlink()
            yield db_path
        finally:
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(f"{db_path}{suffix}")
                if candidate.exists():
                    candidate.unlink()

    def test_dry_run_persists_trace_and_debug_run(self) -> None:
        with self._workspace_db_path() as db_path:
            orchestrator = build_orchestrator(db_path)
            trace = orchestrator.run(
                WorkflowRequest(user_request="开始做周报", run_mode=RunMode.DRY_RUN)
            )

            storage = SQLiteStorage(db_path=db_path)
            loaded_trace = storage.get_trace(trace.trace_id)
            debug_runs = storage.list_debug_runs(trace.trace_id)

            self.assertEqual(loaded_trace.status, WorkflowStatus.DRY_RUN_READY)
            self.assertEqual(len(loaded_trace.planner_result.action_plan.steps), 3)
            self.assertGreaterEqual(len(debug_runs), 2)
            self.assertTrue(debug_runs[0].created_at)
            self.assertTrue(debug_runs[0].updated_at)

    def test_normal_mode_persists_step_results(self) -> None:
        with self._workspace_db_path() as db_path:
            orchestrator = build_orchestrator(db_path)
            trace = orchestrator.run(
                WorkflowRequest(user_request="开始写作", run_mode=RunMode.NORMAL)
            )

            storage = SQLiteStorage(db_path=db_path)
            loaded_trace = storage.get_trace(trace.trace_id)

            self.assertEqual(loaded_trace.status, WorkflowStatus.COMPLETED)
            self.assertEqual(len(loaded_trace.step_results), 3)

    def test_list_recent_traces_returns_newest_first_with_limit(self) -> None:
        with self._workspace_db_path() as db_path:
            orchestrator = build_orchestrator(db_path)
            first = orchestrator.run(
                WorkflowRequest(user_request="开始做周报", run_mode=RunMode.DRY_RUN)
            )
            second = orchestrator.run(
                WorkflowRequest(user_request="开始写作", run_mode=RunMode.DRY_RUN)
            )

            storage = SQLiteStorage(db_path=db_path)
            recent = storage.list_recent_traces(limit=1)

            self.assertEqual(len(recent), 1)
            self.assertEqual(recent[0].trace_id, second.trace_id)
            self.assertEqual(recent[0].trace.request.user_request, "开始写作")
            self.assertNotEqual(recent[0].trace_id, first.trace_id)

    def test_list_debug_runs_filters_by_trace_id(self) -> None:
        with self._workspace_db_path() as db_path:
            orchestrator = build_orchestrator(db_path)
            first = orchestrator.run(
                WorkflowRequest(user_request="开始做周报", run_mode=RunMode.DRY_RUN)
            )
            second = orchestrator.run(
                WorkflowRequest(user_request="开始写作", run_mode=RunMode.DRY_RUN)
            )

            storage = SQLiteStorage(db_path=db_path)
            first_debug_runs = storage.list_debug_runs(first.trace_id)

            self.assertGreaterEqual(len(first_debug_runs), 2)
            self.assertTrue(all(debug_run.trace_id == first.trace_id for debug_run in first_debug_runs))
            self.assertTrue(all(debug_run.trace_id != second.trace_id for debug_run in first_debug_runs))
            self.assertEqual(first_debug_runs[0].run_mode, RunMode.DRY_RUN)

    def test_initialize_records_sqlite_migration_history(self) -> None:
        base_dir = Path.cwd() / "runtime" / "test_db"
        base_dir.mkdir(parents=True, exist_ok=True)
        db_path = base_dir / f"{uuid4().hex}.db"
        try:
            storage = SQLiteStorage(db_path=db_path)
            self.assertTrue(storage.db_path.exists())

            with connect_sqlite(db_path) as connection:
                rows = list_sqlite_migrations(connection)

            self.assertEqual([row["version"] for row in rows], [1, 2, 3, 4, 5])
            self.assertEqual(rows[0]["name"], "workflow_storage")
            self.assertEqual(rows[-1]["name"], "storage_metadata")
            self.assertTrue(rows[-1]["applied_at"])
        finally:
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(f"{db_path}{suffix}")
                if candidate.exists():
                    try:
                        candidate.unlink()
                    except PermissionError:
                        pass

    def test_backfills_migration_history_from_existing_user_version(self) -> None:
        base_dir = Path.cwd() / "runtime" / "test_db"
        base_dir.mkdir(parents=True, exist_ok=True)
        db_path = base_dir / f"{uuid4().hex}.db"
        try:
            with connect_sqlite(db_path) as connection:
                connection.execute("PRAGMA user_version = 3")
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
                ensure_sqlite_schema(connection)
                rows = list_sqlite_migrations(connection)

            self.assertEqual([row["version"] for row in rows], [1, 2, 3, 4, 5])
            self.assertEqual(rows[2]["name"], "workspace_drafts")
        finally:
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(f"{db_path}{suffix}")
                if candidate.exists():
                    try:
                        candidate.unlink()
                    except PermissionError:
                        pass


if __name__ == "__main__":
    unittest.main()
