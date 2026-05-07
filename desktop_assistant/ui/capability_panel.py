from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from ..adapters.windows_app_discovery import ApplicationInventoryStore
from ..adapters.windows_executor import WindowsExecutor
from ..capability.store import CapabilityStore
from ..models import ActionType
from .view_model import (
    capability_detail_to_plain_text,
    capability_label,
    summarize_capability_registry,
)


class CapabilityPanelMixin:
    def _ensure_app_inventory_cache(self) -> None:
        try:
            inventory = ApplicationInventoryStore().ensure(refresh=False)
        except Exception as exc:  # noqa: BLE001 - app inventory should not block the UI
            self.app_inventory_error = f"{type(exc).__name__}: {exc}"
            self.app_inventory_count = 0
            return
        self.app_inventory_error = None
        self.app_inventory_count = len(inventory.applications)

    def _ensure_capability_catalog(self) -> None:
        store = CapabilityStore()
        self.capability_catalog_path = str(store.path)
        try:
            registry = store.ensure(available_handler_names=WindowsExecutor.available_handler_names())
        except Exception as exc:  # noqa: BLE001 - capability catalog should recover on next startup
            self.capability_catalog_error = f"{type(exc).__name__}: {exc}"
            self.enabled_capability_count = 0
            self.capability_summaries = []
            return
        self.capability_catalog_error = None
        self.enabled_capability_count = len(registry.enabled_capabilities())
        self.capability_summaries = summarize_capability_registry(
            registry,
            catalog_path=self.capability_catalog_path,
            available_handler_names=WindowsExecutor.available_handler_names(),
            recent_traces=self._recent_trace_records_for_capabilities(),
        )

    def _recent_trace_records_for_capabilities(self):
        try:
            return self.storage.list_recent_traces(limit=50)
        except Exception:  # noqa: BLE001 - capability diagnostics should not block startup
            return []

    def _refresh_capability_catalog(self) -> None:
        self._ensure_capability_catalog()
        if hasattr(self, "capability_badge"):
            if self.capability_catalog_error:
                self.capability_badge.setText("能力目录不可用")
            else:
                self.capability_badge.setText(f"能力：{self.enabled_capability_count}")
        self._refresh_capability_list()

    def _refresh_capability_list(self) -> None:
        if not hasattr(self, "capability_list"):
            return
        previous_action = self.selected_capability_action
        self.capability_list.clear()
        self.capability_records.clear()

        if self.capability_catalog_error:
            self.capability_count_label.setText("能力目录不可用")
            self.selected_capability_action = None
            self._set_capability_editor_enabled(False)
            self.debug_snapshot_text.setPlainText(
                f"能力目录不可用：\n{self.capability_catalog_error}"
            )
            return

        enabled_count = sum(1 for summary in self.capability_summaries if summary.enabled)
        disabled_count = len(self.capability_summaries) - enabled_count
        missing_count = sum(1 for summary in self.capability_summaries if summary.handler_status == "missing")
        failure_count = sum(summary.recent_failure_count for summary in self.capability_summaries)
        self.capability_count_label.setText(
            f"启用 {enabled_count} / 停用 {disabled_count} / "
            f"未接入 {missing_count} / 近期失败 {failure_count}"
        )
        for summary in self.capability_summaries:
            self.capability_records[summary.action_type] = summary
            item = QListWidgetItem(capability_label(summary))
            item.setData(Qt.ItemDataRole.UserRole, summary.action_type)
            item.setToolTip(
                f"{summary.title}\n"
                f"handler={summary.handler_name}\n"
                f"健康状态={summary.health_label}\n"
                f"执行方式={summary.execution_mode}\n"
                f"近期失败={summary.recent_failure_count}"
            )
            self.capability_list.addItem(item)
        if not self.capability_summaries:
            self.selected_capability_action = None
            self._set_capability_editor_enabled(False)
        elif previous_action in self.capability_records:
            self._select_capability(str(previous_action))
        else:
            self.selected_capability_action = None
            self._set_capability_editor_enabled(False)

    def load_capability_detail(self, item: QListWidgetItem) -> None:
        action_type = item.data(Qt.ItemDataRole.UserRole)
        if not action_type:
            return
        summary = self.capability_records.get(str(action_type))
        if summary is None:
            return
        self.selected_capability_action = summary.action_type
        self.capability_mode_combo.setCurrentText(summary.execution_mode)
        self.capability_risk_combo.setCurrentText(summary.default_risk)
        self.capability_description_input.setText(summary.description)
        self._set_capability_editor_enabled(True)
        self.debug_snapshot_text.setPlainText(capability_detail_to_plain_text(summary))

    def _set_capability_editor_enabled(self, enabled: bool) -> None:
        if not all(
            hasattr(self, name)
            for name in [
                "capability_mode_combo",
                "capability_risk_combo",
                "capability_description_input",
                "save_capability_button",
            ]
        ):
            return
        self.capability_mode_combo.setEnabled(enabled)
        self.capability_risk_combo.setEnabled(enabled)
        self.capability_description_input.setEnabled(enabled)
        self.save_capability_button.setEnabled(enabled)
        if not enabled:
            self.capability_description_input.clear()

    def save_selected_capability(self) -> None:
        if not self.selected_capability_action:
            self.debug_snapshot_text.setPlainText("请先选择一个能力。")
            return

        try:
            action_type = ActionType(str(self.selected_capability_action))
        except ValueError:
            self.debug_snapshot_text.setPlainText(
                f"未知能力动作：{self.selected_capability_action}"
            )
            return

        store = CapabilityStore()
        self.capability_catalog_path = str(store.path)
        try:
            registry = store.update_capability(
                action_type,
                execution_mode=self.capability_mode_combo.currentText(),
                default_risk=self.capability_risk_combo.currentText(),
                description=self.capability_description_input.text().strip(),
                available_handler_names=WindowsExecutor.available_handler_names(),
            )
        except Exception as exc:  # noqa: BLE001 - keep catalog editor failures visible in the UI
            self.capability_catalog_error = f"{type(exc).__name__}: {exc}"
            self.debug_snapshot_text.setPlainText(
                f"保存能力目录失败：\n{self.capability_catalog_error}"
            )
            return

        self.capability_catalog_error = None
        self.enabled_capability_count = len(registry.enabled_capabilities())
        self.capability_summaries = summarize_capability_registry(
            registry,
            catalog_path=self.capability_catalog_path,
            available_handler_names=WindowsExecutor.available_handler_names(),
            recent_traces=self._recent_trace_records_for_capabilities(),
        )
        self.capability_badge.setText(f"能力：{self.enabled_capability_count}")
        self._refresh_capability_list()
        self._select_capability(action_type.value)
        self.summary_label.setText(f"已保存能力：{action_type.value}。")

    def _select_capability(self, action_type: str) -> None:
        for index in range(self.capability_list.count()):
            item = self.capability_list.item(index)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == action_type:
                self.capability_list.setCurrentItem(item)
                self.load_capability_detail(item)
                return
