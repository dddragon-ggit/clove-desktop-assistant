from __future__ import annotations

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QFrame, QLabel, QTableWidgetItem, QVBoxLayout

from ..action_trust import ActionTrustStore
from ..models import RiskLevel, RunMode, WorkflowRequest
from .view_model import WorkflowSummary
from .workers import DryRunWorker, ExecuteTraceWorker, worker_failure_debug_text


class MainWindowInteractionMixin:
    def run_dry_run(self) -> None:
        user_request = self.request_input.text().strip()
        if not user_request:
            self.set_error("Request is empty.")
            return
        self.active_recipe_id = None
        self.active_draft_goal = user_request
        self.active_draft_refinements = []
        self._run_workflow_dry_run(
            WorkflowRequest(user_request=user_request, run_mode=RunMode.DRY_RUN)
        )

    def _run_workflow_dry_run(self, request: WorkflowRequest) -> None:
        self.active_operation = "real dry run" if self.backend_combo.currentText() == "real" else "fake dry run"
        self.running_seconds = 0
        self._set_running(True)
        self.status_badge.setText("Planning")
        self.risk_badge.setText("Risk: -")
        self.trace_label.setText("Trace: -")
        self.summary_label.setText("Planner, policy, and reviewer are checking the request.")
        self.latest_summary = None
        self.action_table.setRowCount(0)
        self.policy_value.setText("Pending")
        self.review_value.setText("Pending")
        self.issues_text.setPlainText("Running dry-run...")
        self.confirmation_label.setText("No plan awaiting decision.")
        self._clear_debug_runs("Waiting for trace...")
        self._set_decision_buttons(False)

        self.worker_thread = QThread()
        self.worker = DryRunWorker(request, self.backend_combo.currentText())
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_dry_run_finished)
        self.worker.failed.connect(self.set_error)
        self.worker.progress.connect(self.set_progress)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(lambda: self._set_running(False))
        self.worker_thread.start()

    def on_dry_run_finished(self, summary: WorkflowSummary) -> None:
        self.latest_summary = summary
        self.status_badge.setText(summary.status)
        self.risk_badge.setText(f"Risk: {summary.policy_risk}")
        self.trace_label.setText(f"Trace: {summary.trace_id[:8]}")
        self.summary_label.setText(
            f"Policy {'approved' if summary.policy_approved else 'blocked'}; "
            f"review {'approved' if summary.review_approved else 'blocked'}."
        )
        self._populate_actions(summary)
        self._populate_review(summary)
        self._populate_confirmation(summary)
        self._refresh_recent_traces()
        self._refresh_debug_runs(summary.trace_id)
        self._update_draft_state_from_trace(summary.trace_id)

    def _update_draft_state_from_trace(self, trace_id: str) -> None:
        try:
            trace = self.storage.get_trace(trace_id)
        except KeyError:
            return
        if trace.request.plan_refinement is not None:
            refinement = trace.request.plan_refinement
            self.active_draft_goal = refinement.original_goal
            self.active_recipe_id = refinement.recipe_id or self.active_recipe_id
            if refinement.user_refinement and refinement.user_refinement not in self.active_draft_refinements:
                self.active_draft_refinements.append(refinement.user_refinement)
            return
        self.active_draft_goal = trace.request.user_request

    def set_error(self, error: object) -> None:
        self.status_badge.setText("Error")
        self.risk_badge.setText("Risk: -")
        self.summary_label.setText("Dry run failed.")
        self.action_table.setRowCount(0)
        self.policy_value.setText("Error")
        self.review_value.setText("Error")
        self.issues_text.setPlainText(worker_failure_debug_text(error))
        self.confirmation_label.setText("No plan awaiting decision.")
        self._clear_debug_runs("No trace selected")
        self._set_decision_buttons(False)

    def set_progress(self, message: str) -> None:
        self.summary_label.setText(message)
        self.issues_text.setPlainText(message)

    def _set_running(self, running: bool) -> None:
        self.run_button.setDisabled(running)
        self.refine_button.setDisabled(running)
        self.request_input.setDisabled(running)
        self.backend_combo.setDisabled(running)
        if running:
            self._set_decision_buttons(False)
            self.progress_timer.start()
        else:
            self.progress_timer.stop()
            self.active_operation = ""

    def _tick_running(self) -> None:
        self.running_seconds += 1
        if self.active_operation == "real dry run":
            self.status_badge.setText(f"Planning {self.running_seconds}s")
            self.summary_label.setText(
                "Real backend is still working "
                f"({self.running_seconds}s): Intent -> Planner -> Reviewer."
            )
        elif self.active_operation:
            self.status_badge.setText(f"Working {self.running_seconds}s")

    def toggle_compact(self) -> None:
        self.is_compact = not self.is_compact
        for widget in [
            self.summary_label,
            self.main_splitter,
        ]:
            widget.setVisible(not self.is_compact)
        self.compact_button.setText("Expand" if self.is_compact else "Collapse")
        if self.is_compact:
            self.expanded_height = max(self.height(), 520)
            self.setFixedHeight(176)
        else:
            self.setMinimumSize(560, 520)
            self.setMaximumHeight(16777215)
            self.resize(self.width(), self.expanded_height)
            self._move_to_bottom_right()

    def _make_detail_panel(self, title: str, initial_text: str) -> QFrame:
        panel = QFrame()
        panel.setObjectName("detailPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 9, 10, 10)
        layout.setSpacing(5)
        title_label = QLabel(title)
        title_label.setObjectName("panelTitle")
        value_label = QLabel(initial_text)
        value_label.setObjectName("panelValue")
        value_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        if title == "Policy":
            self.policy_value = value_label
        else:
            self.review_value = value_label
        return panel

    def _populate_actions(self, summary: WorkflowSummary) -> None:
        self.action_table.setRowCount(len(summary.steps))
        for row, step in enumerate(summary.steps):
            result_text = step.execution_status or "-"
            if step.requires_confirmation:
                result_text = f"{result_text} / confirm"
            elif step.whitelisted:
                result_text = f"{result_text} / trusted"
            values = [step.action_type, step.target, step.risk_level, result_text, step.reason]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(step.execution_message or value)
                self.action_table.setItem(row, column, item)
        self.action_table.resizeRowsToContents()

    def _populate_review(self, summary: WorkflowSummary) -> None:
        self.policy_value.setText(
            f"{'Approved' if summary.policy_approved else 'Blocked'}\n"
            f"Risk: {summary.policy_risk}\n"
            f"Confirmation: {summary.policy_requires_confirmation}"
        )
        self.review_value.setText(
            f"{'Approved' if summary.review_approved else 'Blocked'}\n"
            f"Risk: {summary.review_risk}\n"
            f"Confirmation: {summary.review_needs_confirmation}"
        )

        issue_lines: list[str] = []
        if summary.policy_issues:
            issue_lines.append("Policy issues:")
            issue_lines.extend(f"- {issue}" for issue in summary.policy_issues)
        if summary.review_issues:
            issue_lines.append("Reviewer issues:")
            issue_lines.extend(f"- {issue}" for issue in summary.review_issues)
        if not issue_lines:
            issue_lines.append(summary.review_summary or "No issues.")
        self.issues_text.setPlainText("\n".join(issue_lines))

    def _populate_confirmation(self, summary: WorkflowSummary) -> None:
        if summary.decision_state == "blocked":
            self.confirmation_label.setText("Blocked by policy or reviewer.")
            self._set_decision_buttons(False)
            self.reject_button.setEnabled(True)
            self.save_recipe_button.setEnabled(False)
            return
        if summary.decision_state == "executed":
            self.confirmation_label.setText("Execution completed. Review step results in the action table.")
            self._set_decision_buttons(False)
            self.save_recipe_button.setEnabled(bool(summary.steps))
            return
        if summary.decision_state == "failed":
            self.confirmation_label.setText("Execution failed. Check the action table and debug snapshot.")
            self._set_decision_buttons(False)
            self.save_recipe_button.setEnabled(False)
            return
        if summary.decision_state == "stopped":
            self.confirmation_label.setText("Execution stopped after repeated failures. User correction is required.")
            self._set_decision_buttons(False)
            self.save_recipe_button.setEnabled(False)
            return
        if summary.decision_state == "no_actions":
            self.confirmation_label.setText("No executable actions in this plan.")
            self._set_decision_buttons(False)
            self.reject_button.setEnabled(True)
            self.save_recipe_button.setEnabled(False)
            return
        if summary.decision_state == "needs_confirmation":
            pending = sum(1 for step in summary.steps if step.requires_confirmation)
            self.confirmation_label.setText(f"This plan needs confirmation for {pending} action(s).")
        else:
            self.confirmation_label.setText("This plan is ready for user decision.")
        self._set_decision_buttons(summary.can_run_once)
        self.save_recipe_button.setEnabled(bool(summary.steps))

    def _set_decision_buttons(self, enabled: bool) -> None:
        self.reject_button.setEnabled(enabled)
        self.run_once_button.setEnabled(enabled)
        self.whitelist_button.setEnabled(enabled)
        if hasattr(self, "save_recipe_button"):
            self.save_recipe_button.setEnabled(enabled)

    def record_decision(self, decision: str) -> None:
        if self.latest_summary is None:
            return
        self.status_badge.setText("Decision")
        self.summary_label.setText(f"Decision recorded: {decision}.")
        self.confirmation_label.setText(
            f"{decision.title()} recorded for trace {self.latest_summary.trace_id[:8]}."
        )

    def whitelist_current_actions(self) -> None:
        if self.latest_summary is None:
            return
        try:
            trace = self.storage.get_trace(self.latest_summary.trace_id)
        except KeyError as exc:
            self.set_error(str(exc))
            return

        trusted = 0
        store = ActionTrustStore()
        for decision in trace.policy_decision.action_decisions:
            if decision.risk_level not in {RiskLevel.MEDIUM, RiskLevel.HIGH}:
                continue
            if decision.step_index >= len(trace.planner_result.action_plan.steps):
                continue
            store.trust_action(
                trace.planner_result.action_plan.steps[decision.step_index],
                decision.risk_level,
                note=f"Trusted from trace {trace.trace_id[:8]}",
            )
            trusted += 1

        self.status_badge.setText("Whitelisted")
        self.summary_label.setText(f"Whitelisted {trusted} medium/high-risk action(s).")
        self.confirmation_label.setText(
            "Saved action-level trust rules. Re-run the request to apply them to a fresh plan."
        )

    def run_once_current_trace(self) -> None:
        if self.latest_summary is None:
            return
        if not self.latest_summary.can_run_once:
            self.confirmation_label.setText("This trace is not runnable.")
            return

        self.active_operation = "execution"
        self.running_seconds = 0
        self._set_running(True)
        self.status_badge.setText("Executing")
        self.summary_label.setText("Executing approved low-risk actions.")
        self.confirmation_label.setText("Running once...")
        self.issues_text.setPlainText("Executing actions. Results will appear in the action table.")

        self.worker_thread = QThread()
        self.worker = ExecuteTraceWorker(self.latest_summary.trace_id)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_execution_finished)
        self.worker.failed.connect(self.set_error)
        self.worker.progress.connect(self.set_progress)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(lambda: self._set_running(False))
        self.worker_thread.start()

    def on_execution_finished(self, summary: WorkflowSummary) -> None:
        self.on_dry_run_finished(summary)
        self.summary_label.setText(f"Execution finished for trace {summary.trace_id[:8]}.")
        if self.active_recipe_id:
            recipe = self.recipe_store.get(self.active_recipe_id)
            if recipe is not None:
                recipe.last_run_status = summary.status
                failed_steps = [step for step in summary.steps if step.execution_status == "failed"]
                recipe.last_run_message = (
                    failed_steps[0].execution_message
                    if failed_steps
                    else f"Last run finished with status {summary.status}."
                )
                self.recipe_store.upsert(recipe)
                self._refresh_recipe_list()
