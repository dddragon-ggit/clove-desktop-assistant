from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QListWidgetItem

from ..confirmation import ConfirmationChoice
from ..todo import TodoItem, parse_todo_time, workspace_hint_from_plan, workspace_hint_has_targets
from ..workspace import WorkspaceSuggestion
from . import shell_text as text
from .localization import execution_status_label
from .shell_workspace_actions import (
    append_action_from_input,
    edited_suggestion,
    populate_action_list,
)
from .shell_workspace_confirm import ShellWorkspaceConfirmMixin
from .shell_workspace_target import browse_target, configure_target_input, set_target_text, target_text
from .shell_todo_view import (
    todo_confirmation_message,
    todo_detail_text,
    todo_editable_time,
    todo_short_time,
)
from .shell_todo_items import todo_item_color
from .workers import WorkspaceExecuteWorker, WorkspaceExecutionSummary, worker_failure_text


class ShellTodoMixin(ShellWorkspaceConfirmMixin):
    def _populate_todos(self, todos: list[TodoItem]) -> None:
        selected_id = self._selected_todo_id() if hasattr(self, "todo_list") else None
        self.todo_list.clear()
        selected_row = -1
        logical_today = self._current_todo_logical_date()
        daily_items = [item for item in todos if item.is_daily()]
        temporary_items = [item for item in todos if not item.is_daily()]
        row = 0
        if daily_items:
            self._add_todo_section_header(text.TODO_DAILY_TASK)
            row += 1
            for item in daily_items:
                self._add_todo_item(item, logical_today)
                if item.id == selected_id:
                    selected_row = row
                row += 1
        if temporary_items:
            self._add_todo_section_header(text.TODO_TEMPORARY_TASK)
            row += 1
            for item in temporary_items:
                self._add_todo_item(item, logical_today)
                if item.id == selected_id:
                    selected_row = row
                row += 1
        if selected_row >= 0:
            self.todo_list.setCurrentRow(selected_row)

    def _add_todo_section_header(self, label: str) -> None:
        header = QListWidgetItem(label)
        header.setFlags(Qt.ItemFlag.NoItemFlags)
        font = QFont("Microsoft YaHei UI", 11)
        font.setWeight(QFont.Weight.DemiBold)
        header.setFont(font)
        header.setForeground(QColor(180, 211, 255, 200))
        header.setData(Qt.ItemDataRole.UserRole, "__section_header__")
        self.todo_list.addItem(header)

    def _add_todo_item(self, item: TodoItem, logical_today: str) -> None:
        status_suffix = f" · {text.TODO_DAILY_DONE_TODAY}" if item.is_daily_completed_today() else ""
        entry = QListWidgetItem(
            text.todo_list_text(
                title=f"{item.title}{self._todo_status_suffix(item, logical_today, status_suffix)}",
                priority=item.priority.value,
                important=item.is_important(),
                next_time=todo_short_time(item.next_time()),
            )
        )
        entry.setData(Qt.ItemDataRole.UserRole, item.id)
        entry.setBackground(todo_item_color(item))
        self.todo_list.addItem(entry)

    def _current_todo_logical_date(self) -> str:
        current = datetime.now(UTC)
        try:
            return self.controller.reminder_settings().logical_date(current)
        except Exception:  # noqa: BLE001 - corrupt settings should not break list rendering.
            return current.astimezone().date().isoformat()

    def _todo_status_suffix(self, item: TodoItem, logical_today: str, fallback: str) -> str:
        if not item.is_daily():
            return fallback
        return f" · {text.TODO_DAILY_DONE_TODAY}" if item.daily_completed_on == logical_today else ""

    def _quick_add_todo(self) -> None:
        title = self.todo_quick_input.text().strip()
        if not title:
            self._set_todo_feedback(text.TODO_EMPTY_TITLE)
            self.todo_quick_input.setFocus()
            return
        try:
            todo = self.controller.add_todo(title, task_type=str(self.todo_quick_type_combo.currentData() or "temporary"))
        except Exception as exc:  # noqa: BLE001 - compact shell should surface storage errors.
            self._set_todo_feedback(text.TODO_ADD_FAILED.format(error=f"{type(exc).__name__}: {exc}"))
            return
        self.todo_quick_input.clear()
        self._refresh_home()
        self._select_todo(todo.id)
        current_item = self.todo_list.currentItem()
        if current_item is not None:
            self.todo_list.scrollToItem(current_item)
        self._set_todo_feedback(text.TODO_ADDED.format(title=todo.title))
        self.trigger_pet_action("waving")

    def _add_todo(self) -> None:
        title = self.todo_input.text().strip()
        if not title:
            self._set_todo_feedback(text.TODO_EMPTY_TITLE)
            return
        raw_time = self.todo_time_input.text().strip()
        reminder_at = parse_todo_time(raw_time)
        if raw_time and reminder_at is None:
            self.todo_detail.setPlainText(text.todo_time_parse_error(raw_time))
            return
        priority = str(self.todo_priority_combo.currentData() or "normal")
        try:
            todo = self.controller.add_todo(
                title,
                description=self.todo_description_input.text().strip(),
                important=self.important_check.isChecked(),
                needs_computer=self.needs_computer_check.isChecked(),
                priority=priority,
                task_type=str(self.todo_type_combo.currentData() or "temporary"),
                reminder_at=reminder_at,
            )
        except Exception as exc:  # noqa: BLE001 - compact shell should surface storage errors.
            self.todo_detail.setPlainText(text.TODO_ADD_FAILED.format(error=f"{type(exc).__name__}: {exc}"))
            return
        self.todo_input.clear()
        self.todo_description_input.clear()
        self.todo_time_input.clear()
        self.todo_priority_combo.setCurrentIndex(0)
        self.todo_type_combo.setCurrentIndex(0)
        self.important_check.setChecked(False)
        self.needs_computer_check.setChecked(False)
        self._refresh_home()
        self._select_todo(todo.id)
        self._set_todo_feedback(text.TODO_ADDED.format(title=todo.title))
        self.trigger_pet_action("waving")

    def _selected_todo_id(self) -> str | None:
        item = self.todo_list.currentItem()
        if item is None:
            return None
        raw = item.data(Qt.ItemDataRole.UserRole)
        if raw is None or raw == "__section_header__":
            return None
        return str(raw)

    def _todo_item_count(self) -> int:
        return sum(
            1 for i in range(self.todo_list.count())
            if self.todo_list.item(i).data(Qt.ItemDataRole.UserRole) != "__section_header__"
        )

    def _todo_item_at(self, logical_index: int) -> QListWidgetItem | None:
        current = 0
        for i in range(self.todo_list.count()):
            item = self.todo_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == "__section_header__":
                continue
            if current == logical_index:
                return item
            current += 1
        return None

    def _todo_actual_row(self, logical_index: int) -> int:
        current = 0
        for i in range(self.todo_list.count()):
            if self.todo_list.item(i).data(Qt.ItemDataRole.UserRole) == "__section_header__":
                continue
            if current == logical_index:
                return i
            current += 1
        return -1

    def _set_todo_feedback(self, message: str) -> None:
        if hasattr(self, "todo_feedback_label"):
            self.todo_feedback_label.setText(message)
            self.todo_feedback_label.setVisible(bool(message.strip()))

    def _back_to_todo_detail(self) -> None:
        if self._selected_todo_id():
            self._ensure_work_panel_size()
            self.stack.setCurrentWidget(self.todo_detail_page)
        else:
            self._show_todo_page()

    def _todo_selection_changed(self) -> None:
        item_id = self._selected_todo_id()
        todo = self.controller.get_todo(item_id) if item_id else None
        if todo is None:
            self.todo_detail.setPlainText(text.TODO_DETAIL_EMPTY)
            self.current_suggestion = None
            self._populate_todo_editor(None)
            populate_action_list(self.workspace_action_list, None)
            self._set_todo_execution_buttons(False, False)
            return
        suggestion = self.controller.workspace_preview_from_todo(todo.id)
        self.current_suggestion = suggestion
        self._populate_todo_editor(todo)
        populate_action_list(self.workspace_action_list, suggestion)
        self._workspace_action_type_changed()
        self._render_todo_detail(todo, suggestion)
        self._set_todo_execution_buttons_for(suggestion)
        self._ensure_todo_detail_geometry()
        self.stack.setCurrentWidget(self.todo_detail_page)

    def _open_todo_route(self, item_id: str) -> bool:
        if not self._select_todo(item_id):
            self._show_todo_page()
            return False
        self._todo_selection_changed()
        suggestion = self._current_edited_suggestion()
        if suggestion is not None and suggestion.plan.steps:
            self.workspace_input.setText(suggestion.goal)
            self._show_workspace_confirmation(suggestion, todo_id=item_id)
        return True

    def _select_todo(self, item_id: str) -> bool:
        for row in range(self.todo_list.count()):
            item = self.todo_list.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole)) == item_id:
                self.todo_list.setCurrentRow(row)
                return True
        self._refresh_home()
        for row in range(self.todo_list.count()):
            item = self.todo_list.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole)) == item_id:
                self.todo_list.setCurrentRow(row)
                return True
        return False

    def _save_selected_todo_changes(self) -> None:
        item_id = self._selected_todo_id()
        if not item_id:
            return
        title = self.todo_input.text().strip()
        if not title:
            self.todo_detail.setPlainText(text.TODO_EMPTY_TITLE)
            return
        raw_time = self.todo_time_input.text().strip()
        reminder_at = parse_todo_time(raw_time)
        if raw_time and reminder_at is None:
            self.todo_detail.setPlainText(text.todo_time_parse_error(raw_time))
            return
        self.controller.update_todo(
            item_id,
            title=title,
            description=self.todo_description_input.text(),
            important=self.important_check.isChecked(),
            priority=str(self.todo_priority_combo.currentData() or "normal"),
            task_type=str(self.todo_type_combo.currentData() or "temporary"),
            needs_computer=self.needs_computer_check.isChecked(),
            reminder_at=reminder_at,
        )
        self._refresh_home()
        self.todo_detail.append(f"\n{text.TODO_CHANGES_SAVED}")

    def _save_selected_workspace_binding(self) -> None:
        item_id = self._selected_todo_id()
        suggestion = self._current_edited_suggestion() if item_id else None
        if item_id is None or suggestion is None:
            return
        workspace = workspace_hint_from_plan(suggestion.plan)
        needs_computer = self.needs_computer_check.isChecked() or workspace_hint_has_targets(workspace)
        self.controller.update_todo_workspace(
            item_id,
            workspace=workspace,
            needs_computer=needs_computer,
        )
        self.needs_computer_check.setChecked(needs_computer)
        self._refresh_home()
        self.todo_detail.append(f"\n{text.TODO_WORKSPACE_BINDING_SAVED}")

    def _cancel_selected_todo(self) -> None:
        item_id = self._selected_todo_id()
        if item_id:
            self.controller.cancel_todo(item_id)
            self._refresh_home()
            self.todo_list.setCurrentRow(-1)
            self.todo_detail.setPlainText(text.TODO_CANCELLED)
            self._populate_todo_editor(None)
            self.trigger_pet_action("jumping")

    def _complete_selected_todo(self) -> None:
        item_id = self._selected_todo_id()
        if item_id:
            self.controller.mark_todo_done(item_id)
            self._refresh_home()
            self.trigger_pet_action("jumping")

    def _postpone_selected_todo(self) -> None:
        item_id = self._selected_todo_id()
        if item_id:
            self.controller.postpone_todo(item_id, minutes=30)
            self._refresh_home()
            self.todo_detail.append(f"\n{text.TODO_POSTPONED}")

    def _skip_selected_todo_today(self) -> None:
        item_id = self._selected_todo_id()
        todo = self.controller.get_todo(item_id) if item_id else None
        if todo is None:
            return
        if not todo.is_daily():
            self.todo_detail.append(f"\n{text.TODO_SKIP_TODAY} 只适用于每日日常。")
            return
        self.controller.skip_todo_today(todo.id)
        self._refresh_home()
        self.todo_detail.append(f"\n{text.TODO_SKIPPED_TODAY}")
        self.trigger_pet_action("jumping")

    def _delete_selected_todo(self) -> None:
        item_id = self._selected_todo_id()
        if not item_id:
            return
        deleted = self.controller.delete_todo(item_id)
        self.current_suggestion = None
        self._refresh_home()
        self.todo_list.setCurrentRow(-1)
        self.todo_detail.setPlainText(text.TODO_DELETED if deleted else text.TODO_DELETE_FAILED)
        self._populate_todo_editor(None)
        populate_action_list(self.workspace_action_list, None)
        set_target_text(self.workspace_action_target_input, "")
        self._set_todo_execution_buttons(False, False)
        self._ensure_compact_panel_geometry()
        self.stack.setCurrentWidget(self.todo_page)
        if deleted:
            self.trigger_pet_action("jumping")

    def _workspace_from_selected_todo(self) -> None:
        item_id = self._selected_todo_id()
        suggestion = self._current_edited_suggestion() if item_id else None
        if suggestion is not None:
            self.current_suggestion = suggestion
            self.workspace_input.setText(suggestion.goal)
            self._show_workspace_confirmation(suggestion, todo_id=item_id)

    def _reject_selected_workspace(self) -> None:
        item_id = self._selected_todo_id()
        if not item_id:
            return
        self.controller.record_todo_execution(
            item_id,
            trace_id="",
            status="rejected",
            message=text.TODO_EXECUTION_REJECTED,
        )
        self._refresh_home()
        self.todo_detail.setPlainText(text.TODO_EXECUTION_REJECTED)

    def _run_selected_workspace_once(self) -> None:
        self._execute_selected_workspace(ConfirmationChoice.RUN_ONCE)

    def _trust_selected_workspace(self) -> None:
        self._execute_selected_workspace(ConfirmationChoice.TRUST_ALWAYS)

    def _execute_selected_workspace(self, choice: ConfirmationChoice) -> None:
        item_id = self._selected_todo_id()
        suggestion = self._current_edited_suggestion() if item_id else None
        if item_id is None or suggestion is None or not suggestion.plan.steps:
            return
        if self.worker_thread is not None and self.worker_thread.isRunning():
            return
        self.hold_pet_state("running")
        self.todo_detail.setPlainText(text.TODO_EXECUTING_WORKSPACE)
        self._set_todo_execution_buttons(False, False)
        self.worker_thread = QThread()
        self.worker = WorkspaceExecuteWorker(suggestion.plan, todo_id=item_id, choice=choice)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._workspace_execution_finished)
        self.worker.failed.connect(self._workspace_execution_failed)
        self.worker.progress.connect(self.todo_detail.setPlainText)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _workspace_execution_finished(self, summary: WorkspaceExecutionSummary) -> None:
        if summary.todo_id:
            self.controller.record_todo_execution(
                summary.todo_id,
                trace_id=summary.trace_id,
                status=summary.status,
                message=summary.message,
                executed_actions=summary.executed_actions,
            )
            if summary.accepted and summary.choice == ConfirmationChoice.TRUST_ALWAYS:
                self.controller.confirm_todo_workspace(summary.todo_id, trusted_action_keys=summary.trusted_keys)
        self._refresh_home()
        self.release_pet_hold()
        self.trigger_pet_action("waving" if summary.accepted else "failed")
        self.todo_detail.setPlainText(
            text.TODO_EXECUTION_RESULT.format(
                status=execution_status_label(summary.status),
                message=summary.message,
            )
        )

    def _workspace_execution_failed(self, error: object) -> None:
        item_id = self._selected_todo_id()
        friendly_message = worker_failure_text(error)
        if item_id:
            self.controller.record_todo_execution(item_id, trace_id="", status="failed", message=friendly_message)
        self._refresh_home()
        self.release_pet_hold()
        self.trigger_pet_action("failed")
        self.todo_detail.setPlainText(
            text.TODO_EXECUTION_RESULT.format(status=execution_status_label("failed"), message=friendly_message)
        )

    def _render_todo_detail(self, todo: TodoItem, suggestion: WorkspaceSuggestion | None) -> None:
        self.todo_detail.setPlainText(todo_detail_text(todo, suggestion, todo_confirmation_message(self.controller, suggestion)))

    def _add_workspace_action(self) -> None:
        action_type = str(self.workspace_action_type_combo.currentData() or "")
        target = self._normalized_workspace_action_target(action_type, target_text(self.workspace_action_target_input))
        if append_action_from_input(
            self.workspace_action_list,
            action_type,
            target,
        ):
            set_target_text(self.workspace_action_target_input, "")
            self._workspace_action_selection_changed()

    def _workspace_action_type_changed(self) -> None:
        action_type = str(self.workspace_action_type_combo.currentData() or "")
        configure_target_input(
            self.workspace_action_target_input,
            action_type,
            self.controller.app_options() if action_type in {"open_app", "focus_app"} else [],
            self.workspace_action_browse_button,
        )

    def _browse_workspace_action_target(self) -> None:
        action_type = str(self.workspace_action_type_combo.currentData() or "")
        selected = browse_target(self, action_type)
        if selected:
            set_target_text(self.workspace_action_target_input, selected)

    def _normalized_workspace_action_target(self, action_type: str, target: str) -> str:
        if action_type in {"open_app", "focus_app"}:
            return self.controller.resolve_app_name(target)
        return target.strip()

    def _workspace_action_selection_changed(self) -> None:
        item_id = self._selected_todo_id()
        todo = self.controller.get_todo(item_id) if item_id else None
        suggestion = self._current_edited_suggestion()
        if todo is not None:
            self._render_todo_detail(todo, suggestion)
        self._set_todo_execution_buttons_for(suggestion)

    def _current_edited_suggestion(self) -> WorkspaceSuggestion | None:
        return edited_suggestion(self.current_suggestion, self.workspace_action_list)

    def _set_todo_execution_buttons_for(self, suggestion: WorkspaceSuggestion | None) -> None:
        if suggestion is None or not suggestion.plan.steps:
            self._set_todo_execution_buttons(False, False)
            return
        flow = self.controller.build_confirmation_flow(suggestion)
        self._set_todo_execution_buttons(
            flow.approved_by_policy and ConfirmationChoice.RUN_ONCE in flow.choices,
            flow.approved_by_policy and ConfirmationChoice.TRUST_ALWAYS in flow.choices,
        )

    def _set_todo_execution_buttons(self, run_enabled: bool, trust_enabled: bool) -> None:
        self.todo_reject_button.setEnabled(run_enabled or trust_enabled)
        self.todo_run_once_button.setEnabled(run_enabled)
        self.todo_trust_button.setEnabled(trust_enabled)

    def _populate_todo_editor(self, todo: TodoItem | None) -> None:
        if todo is None:
            self.todo_input.clear()
            self.todo_description_input.clear()
            self.todo_time_input.clear()
            self.todo_priority_combo.setCurrentIndex(0)
            self.todo_type_combo.setCurrentIndex(0)
            self.important_check.setChecked(False)
            self.needs_computer_check.setChecked(False)
            self._set_todo_edit_buttons(False)
            return
        self.todo_input.setText(todo.title)
        self.todo_description_input.setText(todo.description)
        self.todo_time_input.setText(todo_editable_time(todo.next_time()))
        priority_index = self.todo_priority_combo.findData(todo.priority.value)
        self.todo_priority_combo.setCurrentIndex(max(priority_index, 0))
        type_index = self.todo_type_combo.findData(todo.task_type.value)
        self.todo_type_combo.setCurrentIndex(max(type_index, 0))
        self.important_check.setChecked(todo.important)
        self.needs_computer_check.setChecked(todo.needs_computer)
        self._set_todo_edit_buttons(True)

    def _set_todo_edit_buttons(self, enabled: bool) -> None:
        self.todo_save_button.setEnabled(enabled)
        self.todo_cancel_item_button.setEnabled(enabled)
        self.todo_save_workspace_button.setEnabled(enabled)
