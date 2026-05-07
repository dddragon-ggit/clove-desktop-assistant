from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from ..recipe import WorkflowRecipe
from .display_text import recipe_detail_text, recipe_label
from .recipe_table_panel import RecipeTableMixin
from .recipe_workflow_panel import RecipeWorkflowMixin


class RecipePanelMixin(RecipeWorkflowMixin, RecipeTableMixin):
    def _refresh_recipe_list(self) -> None:
        if not hasattr(self, "recipe_list"):
            return
        previous_recipe_id = self.selected_recipe_id
        self.recipe_list.clear()
        self.recipe_records.clear()
        try:
            recipes = self.recipe_store.load()
        except Exception as exc:  # noqa: BLE001 - editor should show corrupt stores clearly
            self.recipe_count_label.setText("方案不可用")
            self._set_recipe_buttons(False)
            self.debug_snapshot_text.setPlainText(f"方案库不可用：\n{type(exc).__name__}: {exc}")
            return

        self.recipe_count_label.setText(f"已保存 {len(recipes)} 个方案")
        for recipe in recipes:
            self.recipe_records[recipe.id] = recipe
            item = QListWidgetItem(recipe_label(recipe))
            item.setData(Qt.ItemDataRole.UserRole, recipe.id)
            item.setToolTip(f"{recipe.name}\n{recipe.user_goal}\n{len(recipe.plan.steps)} 个动作")
            self.recipe_list.addItem(item)
        if previous_recipe_id in self.recipe_records:
            self._select_recipe(str(previous_recipe_id))
        else:
            self.selected_recipe_id = None
            self._set_recipe_buttons(False)

    def load_recipe_detail(self, item: QListWidgetItem) -> None:
        recipe_id = item.data(Qt.ItemDataRole.UserRole)
        if not recipe_id:
            return
        recipe = self.recipe_records.get(str(recipe_id))
        if recipe is None:
            return
        self.selected_recipe_id = recipe.id
        self._set_recipe_buttons(True)
        self._populate_recipe_action_table(recipe)
        self.debug_snapshot_text.setPlainText(recipe_detail_text(recipe))

    def _select_recipe(self, recipe_id: str) -> None:
        for index in range(self.recipe_list.count()):
            item = self.recipe_list.item(index)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == recipe_id:
                self.recipe_list.setCurrentItem(item)
                self.load_recipe_detail(item)
                return

    def _set_recipe_buttons(self, enabled: bool) -> None:
        if not all(
            hasattr(self, name)
            for name in [
                "load_recipe_button",
                "edit_recipe_button",
                "delete_recipe_button",
                "save_recipe_edits_button",
                "check_recipe_button",
                "move_recipe_step_up_button",
                "move_recipe_step_down_button",
                "delete_recipe_step_button",
            ]
        ):
            return
        self.load_recipe_button.setEnabled(enabled)
        self.edit_recipe_button.setEnabled(enabled)
        self.delete_recipe_button.setEnabled(enabled)
        self.save_recipe_edits_button.setEnabled(enabled)
        self.check_recipe_button.setEnabled(enabled)
        self.move_recipe_step_up_button.setEnabled(enabled)
        self.move_recipe_step_down_button.setEnabled(enabled)
        self.delete_recipe_step_button.setEnabled(enabled)

    def _selected_recipe(self) -> WorkflowRecipe | None:
        if not self.selected_recipe_id:
            self.debug_snapshot_text.setPlainText("请先选择一个方案。")
            return None
        recipe = self.recipe_records.get(self.selected_recipe_id) or self.recipe_store.get(self.selected_recipe_id)
        if recipe is None:
            self.debug_snapshot_text.setPlainText("选中的方案已经不存在。")
            return None
        return recipe
