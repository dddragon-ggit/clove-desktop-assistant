from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from ..action_trust import ActionTrustStore
from .display_text import trusted_action_detail_text, trusted_action_label


class TrustPanelMixin:
    def _refresh_trust_list(self) -> None:
        if not hasattr(self, "whitelist_list"):
            return
        previous_key = self.selected_trust_key
        self.whitelist_list.clear()
        self.trust_records.clear()
        try:
            rules = ActionTrustStore().load()
        except Exception as exc:  # noqa: BLE001 - whitelist editor should show corrupt stores clearly
            self.whitelist_count_label.setText("Whitelist unavailable")
            self._set_trust_buttons(False)
            self.debug_snapshot_text.setPlainText(f"Whitelist unavailable:\n{type(exc).__name__}: {exc}")
            return

        self.whitelist_count_label.setText(f"{len(rules)} trusted")
        for rule in rules:
            self.trust_records[rule.key] = rule
            item = QListWidgetItem(trusted_action_label(rule))
            item.setData(Qt.ItemDataRole.UserRole, rule.key)
            item.setToolTip(f"{rule.action_type} -> {rule.target}\n{rule.created_at}\n{rule.note}")
            self.whitelist_list.addItem(item)
        if previous_key in self.trust_records:
            self._select_trust(str(previous_key))
        else:
            self.selected_trust_key = None
            self._set_trust_buttons(False)

    def load_trust_detail(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        if not key:
            return
        rule = self.trust_records.get(str(key))
        if rule is None:
            return
        self.selected_trust_key = rule.key
        self._set_trust_buttons(True)
        self.debug_snapshot_text.setPlainText(trusted_action_detail_text(rule))

    def delete_selected_trust(self) -> None:
        if not self.selected_trust_key:
            self.debug_snapshot_text.setPlainText("Select a trusted action first.")
            return
        rule = self.trust_records.get(self.selected_trust_key)
        deleted = ActionTrustStore().delete(self.selected_trust_key)
        label = f"{rule.action_type}:{rule.target}" if rule is not None else self.selected_trust_key[:8]
        self.selected_trust_key = None
        self._refresh_trust_list()
        self.summary_label.setText(f"Revoked trusted action: {label}" if deleted else f"Trusted action not found: {label}")

    def _select_trust(self, key: str) -> None:
        for index in range(self.whitelist_list.count()):
            item = self.whitelist_list.item(index)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == key:
                self.whitelist_list.setCurrentItem(item)
                self.load_trust_detail(item)
                return

    def _set_trust_buttons(self, enabled: bool) -> None:
        if hasattr(self, "delete_trust_button"):
            self.delete_trust_button.setEnabled(enabled)
