from __future__ import annotations

from PySide6.QtCore import QTimer

from ..confirmation import ConfirmationChoice, ConfirmationFlow
from ..workspace import WorkspaceSuggestion
from . import shell_text as text
from .execution_feedback import workspace_execution_feedback
from .execution_remedies import ExecutionRemedy, remedies_for_results, remedy_lines
from .localization import execution_status_label, localized_text, risk_label
from .shell_workspace_target import set_target_text
from .workers import WorkspaceExecuteWorker, WorkspaceExecutionSummary, worker_failure_text


class ShellWorkspaceConfirmMixin:
    def _show_workspace_confirmation(
        self,
        suggestion: WorkspaceSuggestion,
        *,
        todo_id: str | None = None,
        return_to: str | None = None,
    ) -> None:
        self.confirm_suggestion = suggestion
        self.confirm_todo_id = todo_id
        if todo_id is not None:
            self.confirm_return_target = "todo"
        else:
            self.confirm_return_target = return_to or "workspace"
        flow = self.controller.build_confirmation_flow(suggestion)
        self.workspace_confirm_text.setPlainText(workspace_confirmation_preview(suggestion, flow))
        self._render_workspace_remedies([])
        self._set_workspace_confirm_buttons(
            reject_enabled=bool(suggestion.plan.steps),
            run_enabled=flow.approved_by_policy and ConfirmationChoice.RUN_ONCE in flow.choices,
            trust_enabled=flow.approved_by_policy and ConfirmationChoice.TRUST_ALWAYS in flow.choices,
        )
        self._ensure_work_panel_size()
        self.stack.setCurrentWidget(self.workspace_confirm_page)

    def _back_from_workspace_confirmation(self) -> None:
        target = getattr(
            self,
            "confirm_return_target",
            "workspace" if getattr(self, "confirm_return_to_workspace", False) else "todo",
        )
        if target == "menu":
            self._show_menu()
        elif target == "workspace":
            self._show_workspace_page()
        else:
            self._back_to_todo_detail()

    def _reject_confirmed_workspace(self) -> None:
        item_id = getattr(self, "confirm_todo_id", None)
        if item_id:
            self.controller.record_todo_execution(
                item_id,
                trace_id="",
                status="rejected",
                message=text.TODO_EXECUTION_REJECTED,
            )
        self._refresh_home()
        if item_id:
            self.todo_detail.setPlainText(text.TODO_EXECUTION_REJECTED)
        self.workspace_confirm_text.setPlainText(text.TODO_EXECUTION_REJECTED)
        self._set_workspace_confirm_buttons(reject_enabled=False, run_enabled=False, trust_enabled=False)

    def _run_confirmed_workspace_once(self) -> None:
        self._execute_confirmed_workspace(ConfirmationChoice.RUN_ONCE)

    def _trust_confirmed_workspace(self) -> None:
        self._execute_confirmed_workspace(ConfirmationChoice.TRUST_ALWAYS)

    def _execute_confirmed_workspace(self, choice: ConfirmationChoice) -> None:
        item_id = getattr(self, "confirm_todo_id", None)
        suggestion = getattr(self, "confirm_suggestion", None)
        if suggestion is None or not suggestion.plan.steps:
            return
        if self.worker_thread is not None and self.worker_thread.isRunning():
            return
        self.hold_pet_state("running")
        self.workspace_confirm_text.setPlainText(text.TODO_EXECUTING_WORKSPACE)
        self._set_workspace_confirm_buttons(reject_enabled=False, run_enabled=False, trust_enabled=False)
        self.worker_thread = self._new_worker_thread()
        self.worker = WorkspaceExecuteWorker(suggestion.plan, todo_id=item_id, choice=choice)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._workspace_confirm_execution_finished)
        self.worker.failed.connect(self._workspace_confirm_execution_failed)
        self.worker.progress.connect(self.workspace_confirm_text.setPlainText)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _new_worker_thread(self):  # type: ignore[no-untyped-def]
        from PySide6.QtCore import QThread

        return QThread()

    def _workspace_confirm_execution_finished(self, summary: WorkspaceExecutionSummary) -> None:
        self._workspace_execution_finished(summary)
        remedies = remedies_for_results(summary.results)
        message = summary.message
        if remedies and "可以继续：" not in message:
            message = "\n".join([message, *remedy_lines(summary.results)])
        self.workspace_confirm_text.setPlainText(
            text.TODO_EXECUTION_RESULT.format(
                status=execution_status_label(summary.status),
                message=message,
            )
        )
        self._render_workspace_remedies(remedies)

    def _workspace_confirm_execution_failed(self, error: object) -> None:
        item_id = getattr(self, "confirm_todo_id", None)
        friendly_message = worker_failure_text(error)
        if item_id:
            self.controller.record_todo_execution(item_id, trace_id="", status="failed", message=friendly_message)
        self._refresh_home()
        self.release_pet_hold()
        self.trigger_pet_action("failed")
        self.workspace_confirm_text.setPlainText(
            text.TODO_EXECUTION_RESULT.format(status=execution_status_label("failed"), message=friendly_message)
        )
        self._render_workspace_remedies([])

    def _set_workspace_confirm_buttons(self, *, reject_enabled: bool, run_enabled: bool, trust_enabled: bool) -> None:
        self.workspace_confirm_reject_button.setEnabled(reject_enabled)
        self.workspace_confirm_run_button.setEnabled(run_enabled)
        self.workspace_confirm_trust_button.setEnabled(trust_enabled)

    def _render_workspace_remedies(self, remedies: list[ExecutionRemedy]) -> None:
        self.workspace_remedies = remedies
        for index, button in enumerate(getattr(self, "workspace_remedy_buttons", [])):
            remedy = remedies[index] if index < len(remedies) else None
            if remedy is None:
                button.setVisible(False)
                button.setEnabled(False)
                button.setText("")
                button.setToolTip("")
                continue
            button.setText(remedy.label)
            button.setToolTip(remedy.description)
            button.setEnabled(True)
            button.setVisible(True)

    def _run_workspace_remedy_index(self, index: int) -> None:
        remedies = getattr(self, "workspace_remedies", [])
        if index < 0 or index >= len(remedies):
            return
        remedy = remedies[index]
        if remedy.kind == "refresh_app_inventory":
            self.workspace_confirm_text.append(f"\n\n{self.controller.refresh_app_inventory()}")
            self._render_workspace_remedies([])
            return
        if remedy.kind == "select_path":
            self._open_path_remedy(remedy)
            return
        if remedy.kind == "open_capability_debug":
            self.workspace_confirm_text.append(
                "\n\n能力状态：\n" + self.controller.capability_debug_text(remedy.action_type)
            )
            return
        if remedy.action_type is None:
            self.workspace_confirm_text.append(f"\n\n{remedy.description}")
            return
        if remedy.delay_seconds > 0:
            self.workspace_confirm_text.append(f"\n\n已安排：{remedy.label}。")
            for button in getattr(self, "workspace_remedy_buttons", []):
                button.setEnabled(False)
            QTimer.singleShot(remedy.delay_seconds * 1000, lambda item=remedy: self._execute_workspace_remedy(item))
            return
        self._execute_workspace_remedy(remedy)

    def _execute_workspace_remedy(self, remedy: ExecutionRemedy) -> None:
        if remedy.action_type is None:
            return
        result = self.controller.execute_direct_action(
            remedy.action_type,
            remedy.target,
            params=remedy.params,
            risk_level=remedy.risk_level,
            reason=remedy.description,
        )
        self.workspace_confirm_text.append(
            "\n\n补救动作结果：\n" + workspace_execution_feedback([result])
        )
        self._render_workspace_remedies(remedies_for_results([result]))

    def _open_path_remedy(self, remedy: ExecutionRemedy) -> None:
        action_value = remedy.action_type.value if remedy.action_type else ""
        self._back_from_workspace_confirmation()
        if self._fill_visible_path_editor(action_value, remedy.target):
            message = "已回到编辑页，并把失败的路径填回输入框。你可以点“选择”重新挑文件或文件夹。"
        else:
            message = remedy.description
        target = getattr(
            self,
            "confirm_return_target",
            "workspace" if getattr(self, "confirm_return_to_workspace", False) else "todo",
        )
        if target == "workspace":
            self.workspace_text.append(f"\n{message}")
        elif target == "todo":
            self.todo_detail.append(f"\n{message}")

    def _fill_visible_path_editor(self, action_type: str, target: str) -> bool:
        if self.stack.currentWidget() is self.todo_detail_page and hasattr(self, "workspace_action_type_combo"):
            combo = self.workspace_action_type_combo
            index = combo.findData(action_type)
            if index >= 0:
                combo.setCurrentIndex(index)
                self._workspace_action_type_changed()
            set_target_text(self.workspace_action_target_input, target)
            self.workspace_action_target_input.setFocus()
            return True
        if self.stack.currentWidget() is self.workspace_page and hasattr(self, "workspace_plan_action_type_combo"):
            combo = self.workspace_plan_action_type_combo
            index = combo.findData(action_type)
            if index >= 0:
                combo.setCurrentIndex(index)
                self._workspace_plan_action_type_changed()
            set_target_text(self.workspace_plan_action_target_input, target)
            self.workspace_plan_action_target_input.setFocus()
            return True
        return False


def workspace_confirmation_preview(suggestion: WorkspaceSuggestion, flow: ConfirmationFlow) -> str:
    if not suggestion.plan.steps:
        return text.WORKSPACE_CONFIRM_EMPTY
    risk = risk_label(_highest_risk(flow))
    lines = [suggestion.title, text.WORKSPACE_CONFIRM_READY.format(count=len(suggestion.plan.steps), risk=risk)]
    if not flow.approved_by_policy:
        lines.append(text.WORKSPACE_CONFIRM_BLOCKED)
    lines.append("")
    card_by_index = {card.step_index: card for card in flow.action_cards}
    for group, items in _grouped_steps(suggestion):
        lines.append(f"{group}:")
        for step_index, target in items:
            card = card_by_index.get(step_index)
            status = _card_status(card)
            reason = card.reason if card and card.reason else suggestion.plan.steps[step_index].reason
            lines.append(f"{step_index + 1}. {target}")
            lines.append(f"   {status} · {localized_text(reason)}")
        lines.append("")
    if flow.issues:
        lines.append("\n".join(flow.issues))
    return "\n".join(lines).strip()


def _grouped_steps(suggestion: WorkspaceSuggestion) -> list[tuple[str, list[tuple[int, str]]]]:
    groups: dict[str, list[tuple[int, str]]] = {}
    for index, step in enumerate(suggestion.plan.steps):
        groups.setdefault(_group_label(step.action_type.value), []).append((index, step.target))
    return [(label, groups[label]) for label in _group_order() if label in groups]


def _group_label(action_type: str) -> str:
    return {
        "open_app": text.WORKSPACE_GROUP_APPS,
        "focus_app": text.WORKSPACE_GROUP_APPS,
        "open_url": text.WORKSPACE_GROUP_URLS,
        "open_file": text.WORKSPACE_GROUP_FILES,
        "open_folder": text.WORKSPACE_GROUP_FOLDERS,
        "open_project": text.WORKSPACE_GROUP_PROJECTS,
    }.get(action_type, text.WORKSPACE_GROUP_OTHER)


def _group_order() -> list[str]:
    return [
        text.WORKSPACE_GROUP_APPS,
        text.WORKSPACE_GROUP_URLS,
        text.WORKSPACE_GROUP_FILES,
        text.WORKSPACE_GROUP_FOLDERS,
        text.WORKSPACE_GROUP_PROJECTS,
        text.WORKSPACE_GROUP_OTHER,
    ]


def _card_status(card) -> str:  # type: ignore[no-untyped-def]
    if card is None:
        return text.WORKSPACE_CONFIRM_AUTO
    if card.whitelisted:
        return f"{risk_label(card.risk_level)} · {text.WORKSPACE_CONFIRM_TRUSTED}"
    if card.requires_confirmation:
        return f"{risk_label(card.risk_level)} · {text.WORKSPACE_CONFIRM_REQUIRES}"
    return f"{risk_label(card.risk_level)} · {text.WORKSPACE_CONFIRM_AUTO}"


def _highest_risk(flow: ConfirmationFlow) -> str:
    risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    return max((card.risk_level for card in flow.action_cards), key=lambda value: risk_order.get(value, 0), default="low")
