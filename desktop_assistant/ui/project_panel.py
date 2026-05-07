from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QListWidgetItem

from ..projects import ProjectLocation
from .display_text import project_detail_text, project_label


class ProjectPanelMixin:
    def _refresh_project_list(self) -> None:
        if not hasattr(self, "project_list"):
            return
        previous_project_name = self.selected_project_name
        self.project_list.clear()
        self.project_records.clear()
        try:
            locations = self.project_store.ensure()
        except Exception as exc:  # noqa: BLE001 - editor should show corrupt stores clearly
            self.project_count_label.setText("Projects unavailable")
            self._set_project_editor_enabled(False)
            self.debug_snapshot_text.setPlainText(f"Project catalog unavailable:\n{type(exc).__name__}: {exc}")
            return

        self.project_count_label.setText(f"{len(locations)} item(s)")
        for location in locations:
            self.project_records[location.name] = location
            item = QListWidgetItem(project_label(location))
            item.setData(Qt.ItemDataRole.UserRole, location.name)
            item.setToolTip(f"{location.name}\n{location.path}\n{location.description}")
            self.project_list.addItem(item)
        if previous_project_name in self.project_records:
            self._select_project(str(previous_project_name))
        else:
            self.selected_project_name = None
            self._set_project_editor_enabled(False)

    def load_project_detail(self, item: QListWidgetItem) -> None:
        project_name = item.data(Qt.ItemDataRole.UserRole)
        if not project_name:
            return
        location = self.project_records.get(str(project_name))
        if location is None:
            return
        self.selected_project_name = location.name
        self.project_name_input.setText(location.name)
        self.project_path_input.setText(location.path)
        self.project_kind_combo.setCurrentText(location.kind if location.kind in {"project", "folder"} else "folder")
        self.project_description_input.setText(location.description)
        self._set_project_editor_enabled(True)
        self._update_project_path_status(location.path)
        self.debug_snapshot_text.setPlainText(project_detail_text(location))

    def new_project_entry(self) -> None:
        self.selected_project_name = None
        self.project_name_input.clear()
        self.project_path_input.clear()
        self.project_kind_combo.setCurrentText("project")
        self.project_description_input.clear()
        self.project_path_status_label.setText("Path: -")
        self._set_project_editor_enabled(True)
        self.project_name_input.setFocus()
        self.debug_snapshot_text.setPlainText("Create a new project entry, then Save.")

    def browse_project_path(self) -> None:
        initial = self.project_path_input.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Select project folder", initial)
        if not selected:
            return
        self.project_path_input.setText(selected)
        if not self.project_name_input.text().strip():
            self.project_name_input.setText(Path(selected).name or selected)
        self._update_project_path_status(selected)

    def discover_projects(self) -> None:
        try:
            locations = self.project_store.refresh_discovered()
        except Exception as exc:  # noqa: BLE001 - discovery errors should be shown in the diagnostics pane
            self.debug_snapshot_text.setPlainText(f"Project discovery failed:\n{type(exc).__name__}: {exc}")
            return
        self._refresh_project_list()
        self.summary_label.setText(f"Project catalog refreshed with {len(locations)} cached item(s).")
        self.debug_snapshot_text.setPlainText(
            "Project discovery finished. The catalog now includes common folders and detected project roots."
        )

    def save_selected_project(self) -> None:
        name = self.project_name_input.text().strip()
        path = self.project_path_input.text().strip()
        if not name or not path:
            self.debug_snapshot_text.setPlainText("Project name and path are required.")
            return
        path_obj = Path(path).expanduser()
        if not path_obj.exists():
            self._update_project_path_status(path)
            self.debug_snapshot_text.setPlainText(f"Project path does not exist:\n{path_obj}")
            return
        if not path_obj.is_dir():
            self._update_project_path_status(path)
            self.debug_snapshot_text.setPlainText(f"Project path is not a folder:\n{path_obj}")
            return
        location = ProjectLocation(
            name=name,
            path=str(path_obj),
            kind=self.project_kind_combo.currentText(),
            description=self.project_description_input.text().strip(),
        )
        try:
            self.project_store.upsert(location)
        except Exception as exc:  # noqa: BLE001 - keep project save errors visible
            self.debug_snapshot_text.setPlainText(f"Failed to save project:\n{type(exc).__name__}: {exc}")
            return
        self.selected_project_name = location.name
        self._refresh_project_list()
        self._select_project(location.name)
        self.summary_label.setText(f"Saved project: {location.name}")

    def open_selected_project(self) -> None:
        name = self.selected_project_name or self.project_name_input.text().strip()
        if not name:
            self.debug_snapshot_text.setPlainText("Select or enter a project first.")
            return
        self.request_input.setText(f"打开{name}")
        self.run_dry_run()

    def delete_selected_project(self) -> None:
        name = self.selected_project_name or self.project_name_input.text().strip()
        if not name:
            self.debug_snapshot_text.setPlainText("Select a project first.")
            return
        deleted = self.project_store.delete(name)
        self.selected_project_name = None
        self._refresh_project_list()
        self.summary_label.setText(f"Deleted project: {name}" if deleted else f"Project was not found: {name}")
        self.debug_snapshot_text.setPlainText("Select a recipe, project, capability, or debug run to inspect details.")

    def _select_project(self, name: str) -> None:
        for index in range(self.project_list.count()):
            item = self.project_list.item(index)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == name:
                self.project_list.setCurrentItem(item)
                self.load_project_detail(item)
                return

    def _set_project_editor_enabled(self, enabled: bool) -> None:
        if not all(
            hasattr(self, name)
            for name in [
                "project_name_input",
                "project_path_input",
                "project_kind_combo",
                "project_description_input",
                "save_project_button",
                "browse_project_button",
                "open_project_button",
                "delete_project_button",
            ]
        ):
            return
        self.project_name_input.setEnabled(enabled)
        self.project_path_input.setEnabled(enabled)
        self.project_kind_combo.setEnabled(enabled)
        self.project_description_input.setEnabled(enabled)
        self.save_project_button.setEnabled(enabled)
        self.browse_project_button.setEnabled(enabled)
        self.open_project_button.setEnabled(enabled)
        self.delete_project_button.setEnabled(enabled)
        if not enabled:
            self.project_name_input.clear()
            self.project_path_input.clear()
            self.project_description_input.clear()
            if hasattr(self, "project_path_status_label"):
                self.project_path_status_label.setText("Path: -")

    def _update_project_path_status(self, path: str) -> None:
        path_obj = Path(path).expanduser()
        if not path:
            self.project_path_status_label.setText("Path: -")
        elif path_obj.exists() and path_obj.is_dir():
            self.project_path_status_label.setText("Path: OK")
        elif path_obj.exists():
            self.project_path_status_label.setText("Path: not a folder")
        else:
            self.project_path_status_label.setText("Path: missing")
