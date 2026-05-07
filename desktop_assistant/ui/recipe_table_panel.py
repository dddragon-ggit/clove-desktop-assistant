from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from ..adapters.windows_executor import WindowsExecutor
from ..capability.store import CapabilityStore
from ..models import ActionStep, ActionType, RiskLevel
from ..recipe import RecipeRevision, WorkflowRecipe, check_recipe
from .localization import action_label, risk_label


class RecipeTableMixin:
    def _populate_recipe_action_table(self, recipe: WorkflowRecipe) -> None:
        self.recipe_action_table.setRowCount(len(recipe.plan.steps))
        for row, step in enumerate(recipe.plan.steps):
            values = [action_label(step.action_type.value), step.target, risk_label(step.risk_level.value), step.reason]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, step.action_type.value)
                if column == 2:
                    item.setData(Qt.ItemDataRole.UserRole, step.risk_level.value)
                self.recipe_action_table.setItem(row, column, item)
        self.recipe_action_table.resizeRowsToContents()

    def save_recipe_action_edits(self) -> None:
        recipe = self._selected_recipe()
        if recipe is None:
            return
        try:
            steps = self._recipe_steps_from_table(recipe)
        except ValueError as exc:
            self.debug_snapshot_text.setPlainText(str(exc))
            return

        updated_recipe = recipe.model_copy(deep=True)
        updated_recipe.plan.steps = steps
        updated_recipe.revision_history.append(
            RecipeRevision(
                plan_name=updated_recipe.plan.plan_name,
                action_count=len(steps),
                note="Manual action table edit",
            )
        )
        self.recipe_store.upsert(updated_recipe)
        self._refresh_recipe_list()
        self._select_recipe(updated_recipe.id)
        self.summary_label.setText(f"已保存方案动作：{updated_recipe.name}")

    def check_selected_recipe(self) -> None:
        recipe = self._selected_recipe()
        if recipe is None:
            return
        try:
            registry = CapabilityStore().ensure(
                available_handler_names=WindowsExecutor.available_handler_names()
            )
            result = check_recipe(
                recipe,
                capability_registry=registry,
                available_handler_names=WindowsExecutor.available_handler_names(),
                path_exists=lambda raw_path: Path(raw_path).expanduser().exists(),
            )
            updated_recipe = self.recipe_store.update_check_result(recipe.id, result) or recipe
        except Exception as exc:  # noqa: BLE001 - check failures should be visible, not silent
            self.debug_snapshot_text.setPlainText(f"方案检查失败：\n{type(exc).__name__}: {exc}")
            return
        self._refresh_recipe_list()
        self._select_recipe(updated_recipe.id)
        status = "可用" if result.ok else f"{len(result.issues)} 个问题"
        self.summary_label.setText(f"方案检查完成：{status}。")

    def move_selected_recipe_step(self, direction: int) -> None:
        row = self.recipe_action_table.currentRow()
        if row < 0:
            self.debug_snapshot_text.setPlainText("请先选择一个方案动作。")
            return
        target_row = row + direction
        if target_row < 0 or target_row >= self.recipe_action_table.rowCount():
            return
        self._swap_recipe_table_rows(row, target_row)
        self.recipe_action_table.selectRow(target_row)

    def delete_selected_recipe_step(self) -> None:
        row = self.recipe_action_table.currentRow()
        if row < 0:
            self.debug_snapshot_text.setPlainText("请先选择一个方案动作。")
            return
        self.recipe_action_table.removeRow(row)

    def _recipe_steps_from_table(self, recipe: WorkflowRecipe):
        steps = []
        for row in range(self.recipe_action_table.rowCount()):
            action_type_text = self._table_text(self.recipe_action_table, row, 0)
            target = self._table_text(self.recipe_action_table, row, 1)
            risk_text = self._table_text(self.recipe_action_table, row, 2) or RiskLevel.LOW.value
            reason = self._table_text(self.recipe_action_table, row, 3)
            if not action_type_text or not target:
                raise ValueError(f"方案第 {row + 1} 行需要动作和目标。")
            action_type_text = self._table_data(self.recipe_action_table, row, 0) or action_type_text
            risk_text = self._table_data(self.recipe_action_table, row, 2) or risk_text
            try:
                action_type = ActionType(action_type_text)
            except ValueError as exc:
                raise ValueError(f"方案第 {row + 1} 行的动作类型未知：{action_type_text}") from exc
            try:
                risk_level = RiskLevel(risk_text)
            except ValueError as exc:
                raise ValueError(f"方案第 {row + 1} 行的风险等级未知：{risk_text}") from exc
            original = recipe.plan.steps[row] if row < len(recipe.plan.steps) else None
            steps.append(
                ActionStep(
                    action_type=action_type,
                    target=target,
                    params=original.params if original is not None else {},
                    risk_level=risk_level,
                    reason=reason,
                )
            )
        return steps

    @staticmethod
    def _table_text(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return item.text().strip() if item is not None else ""

    @staticmethod
    def _table_data(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        value = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return str(value).strip() if value is not None else ""

    def _swap_recipe_table_rows(self, left: int, right: int) -> None:
        for column in range(self.recipe_action_table.columnCount()):
            left_item = self.recipe_action_table.takeItem(left, column)
            right_item = self.recipe_action_table.takeItem(right, column)
            self.recipe_action_table.setItem(left, column, right_item)
            self.recipe_action_table.setItem(right, column, left_item)
