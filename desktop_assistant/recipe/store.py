from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..models import ActionPlan, ActionStep, RiskLevel
from ..storage import quarantine_corrupted_file, write_json_atomic
from ..storage.sqlite import (
    connect_sqlite,
    default_database_path,
    ensure_sqlite_schema,
    get_storage_metadata,
    set_storage_metadata,
)
from .models import RECIPE_SCHEMA_VERSION, RecipeCheckResult, RecipeRevision, WorkflowRecipe
from .utils import default_recipe_name, default_recipe_store_path, normalize_recipe_query


class RecipeStore:
    """Persist reusable user-confirmed plans."""

    def __init__(self, path: str | Path | None = None) -> None:
        resolved = Path(path) if path is not None else default_database_path()
        self.path = resolved
        self._use_sqlite = resolved.suffix.lower() == ".db" or path is None
        self._legacy_json_path = default_recipe_store_path() if self._use_sqlite and path is None else None
        if self._use_sqlite:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)

    def load(self) -> list[WorkflowRecipe]:
        if self._use_sqlite:
            return self._load_sqlite()
        return self._load_json()

    def _load_json(self) -> list[WorkflowRecipe]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            quarantine_corrupted_file(self.path, source="recipe_store", category="recipe_store_corrupted", reason="Recipe JSON is unreadable.")
            return []
        if not isinstance(payload, dict):
            quarantine_corrupted_file(self.path, source="recipe_store", category="recipe_store_invalid", reason="Recipe JSON root must be an object.")
            return []
        raw_recipes = payload.get("recipes") or []
        if not isinstance(raw_recipes, list):
            quarantine_corrupted_file(self.path, source="recipe_store", category="recipe_store_invalid", reason="Recipe JSON recipes must be a list.")
            return []
        try:
            return [
                WorkflowRecipe.model_validate(item)
                for item in raw_recipes
                if isinstance(item, dict)
            ]
        except Exception:
            quarantine_corrupted_file(self.path, source="recipe_store", category="recipe_store_invalid", reason="Recipe items could not be validated.")
            return []

    def save(self, recipes: Iterable[WorkflowRecipe]) -> None:
        if self._use_sqlite:
            self._save_sqlite(recipes)
            return
        payload = {
            "schema_version": RECIPE_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "recipes": [recipe.model_dump(mode="json") for recipe in recipes],
        }
        write_json_atomic(self.path, payload)

    def upsert(self, recipe: WorkflowRecipe) -> WorkflowRecipe:
        if self._use_sqlite:
            now = datetime.now(UTC).isoformat()
            recipe.updated_at = now
            if not recipe.created_at:
                recipe.created_at = now
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)
                self._maybe_import_legacy_json(connection)
                self._upsert_sqlite(connection, recipe)
            return recipe
        recipes = self.load()
        now = datetime.now(UTC).isoformat()
        recipe.updated_at = now
        if not recipe.created_at:
            recipe.created_at = now

        by_id = {item.id: item for item in recipes}
        by_id[recipe.id] = recipe
        self.save(by_id.values())
        return recipe

    def get(self, recipe_id: str) -> WorkflowRecipe | None:
        if self._use_sqlite:
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)
                self._maybe_import_legacy_json(connection)
                row = connection.execute(
                    "SELECT recipe_json FROM workflow_recipes WHERE recipe_id = ?",
                    (recipe_id,),
                ).fetchone()
            if row is None:
                return None
            return WorkflowRecipe.model_validate(json.loads(row["recipe_json"]))
        for recipe in self.load():
            if recipe.id == recipe_id:
                return recipe
        return None

    def delete(self, recipe_id: str) -> bool:
        if self._use_sqlite:
            with connect_sqlite(self.path) as connection:
                ensure_sqlite_schema(connection)
                self._maybe_import_legacy_json(connection)
                with connection:
                    result = connection.execute(
                        "DELETE FROM workflow_recipes WHERE recipe_id = ?",
                        (recipe_id,),
                    )
            return int(result.rowcount or 0) > 0
        recipes = self.load()
        kept = [recipe for recipe in recipes if recipe.id != recipe_id]
        if len(kept) == len(recipes):
            return False
        self.save(kept)
        return True

    def create_from_steps(
        self,
        *,
        name: str,
        user_goal: str,
        plan_name: str,
        risk_level: RiskLevel,
        steps: Iterable[ActionStep],
        recipe_id: str | None = None,
        description: str = "",
        scenario: str = "",
        previous_revision_history: Iterable[RecipeRevision] | None = None,
        source_trace_id: str | None = None,
        user_refinement: str = "",
        revision_note: str = "",
    ) -> WorkflowRecipe:
        step_list = list(steps)
        revision_history = list(previous_revision_history or [])
        revision_history.append(
            RecipeRevision(
                source_trace_id=source_trace_id,
                user_refinement=user_refinement,
                plan_name=plan_name,
                action_count=len(step_list),
                note=revision_note or ("Refined plan" if user_refinement else "Saved plan"),
            )
        )
        recipe = WorkflowRecipe(
            id=recipe_id or str(uuid4()),
            name=name.strip() or default_recipe_name(user_goal),
            user_goal=user_goal,
            description=description,
            scenario=scenario,
            plan=ActionPlan(plan_name=plan_name, source="saved_recipe", steps=step_list),
            risk_level=risk_level,
            revision_history=revision_history,
        )
        return self.upsert(recipe)

    def update_check_result(self, recipe_id: str, result: RecipeCheckResult) -> WorkflowRecipe | None:
        recipe = self.get(recipe_id)
        if recipe is None:
            return None
        recipe.last_check = result
        return self.upsert(recipe)

    def find(self, query: str) -> WorkflowRecipe | None:
        normalized = normalize_recipe_query(query)
        if not normalized:
            return None
        best: WorkflowRecipe | None = None
        best_score = 0
        for recipe in self.load():
            candidate = normalize_recipe_query(" ".join([recipe.name, recipe.user_goal, recipe.plan.plan_name]))
            score = 0
            if normalize_recipe_query(recipe.name) == normalized:
                score += 100
            if normalized in candidate:
                score += 60
            for token in normalized.split():
                if token in candidate:
                    score += 10
            if score > best_score:
                best_score = score
                best = recipe
        return best

    def _load_sqlite(self) -> list[WorkflowRecipe]:
        with connect_sqlite(self.path) as connection:
            ensure_sqlite_schema(connection)
            self._maybe_import_legacy_json(connection)
            rows = connection.execute(
                "SELECT recipe_json FROM workflow_recipes ORDER BY updated_at DESC"
            ).fetchall()
        return [WorkflowRecipe.model_validate(json.loads(row["recipe_json"])) for row in rows]

    def _save_sqlite(self, recipes: Iterable[WorkflowRecipe]) -> None:
        with connect_sqlite(self.path) as connection:
            ensure_sqlite_schema(connection)
            self._maybe_import_legacy_json(connection)
            with connection:
                connection.execute("DELETE FROM workflow_recipes")
                for recipe in recipes:
                    self._upsert_sqlite(connection, recipe)

    def _maybe_import_legacy_json(self, connection: sqlite3.Connection) -> None:
        if self._legacy_json_path is None or not self._legacy_json_path.exists():
            return
        if get_storage_metadata(connection, "recipe_legacy_json_imported") == "1":
            return
        row = connection.execute("SELECT COUNT(*) AS count FROM workflow_recipes").fetchone()
        if row is not None and int(row["count"] or 0) > 0:
            set_storage_metadata(connection, "recipe_legacy_json_imported", "1")
            return
        legacy_store = RecipeStore(self._legacy_json_path)
        recipes = legacy_store.load()
        with connection:
            for recipe in recipes:
                self._upsert_sqlite(connection, recipe)
            set_storage_metadata(connection, "recipe_legacy_json_imported", "1")

    def _upsert_sqlite(self, connection: sqlite3.Connection, recipe: WorkflowRecipe) -> None:
        payload = json.dumps(recipe.model_dump(mode="json"), ensure_ascii=False)
        connection.execute(
            """
            INSERT INTO workflow_recipes (
                recipe_id,
                scenario,
                name,
                user_goal,
                created_at,
                updated_at,
                recipe_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(recipe_id) DO UPDATE SET
                scenario = excluded.scenario,
                name = excluded.name,
                user_goal = excluded.user_goal,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                recipe_json = excluded.recipe_json
            """,
            (
                recipe.id,
                recipe.scenario,
                recipe.name,
                recipe.user_goal,
                recipe.created_at,
                recipe.updated_at,
                payload,
            ),
        )
