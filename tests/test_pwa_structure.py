"""Tests for PWA HTML structure and JS function presence."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


class TestPwaHtmlStructure(unittest.TestCase):
    """Verify the HTML files contain required UI elements."""

    def _read(self, folder: Path, name: str) -> str:
        return (folder / name).read_text(encoding="utf-8")

    def _assert_element(self, html: str, selector: str, label: str) -> None:
        self.assertIn(selector, html, f"Missing {label}: {selector}")

    def test_edit_modal_in_docs(self):
        html = self._read(DOCS_DIR, "index.html")
        self._assert_element(html, 'id="edit-modal"', "edit modal overlay")
        self._assert_element(html, 'id="edit-title"', "edit title input")
        self._assert_element(html, 'id="edit-desc"', "edit description textarea")
        self._assert_element(html, 'id="edit-type"', "edit type select")
        self._assert_element(html, 'id="edit-priority"', "edit priority select")
        self._assert_element(html, 'id="edit-due"', "edit due date input")
        self._assert_element(html, 'id="modal-save"', "save button")
        self._assert_element(html, 'id="modal-cancel"', "cancel button")

    def test_search_bar_in_docs(self):
        html = self._read(DOCS_DIR, "index.html")
        self._assert_element(html, 'id="search-input"', "search input")
        self.assertIn("搜索任务", html, "search placeholder text")

    def test_filter_tabs_in_docs(self):
        html = self._read(DOCS_DIR, "index.html")
        self._assert_element(html, 'id="filter-tabs"', "filter tabs container")
        self.assertIn('data-filter="all"', html, "all filter tab")
        self.assertIn('data-filter="open"', html, "open filter tab")
        self.assertIn('data-filter="daily"', html, "daily filter tab")
        self.assertIn('data-filter="temporary"', html, "temporary filter tab")
        self.assertIn('data-filter="done"', html, "done filter tab")

    def test_nav_tabs_in_docs(self):
        html = self._read(DOCS_DIR, "index.html")
        self._assert_element(html, 'data-section="todos"', "todos nav tab")
        self._assert_element(html, 'data-section="notes"', "notes nav tab")

    def test_notes_section_in_docs(self):
        html = self._read(DOCS_DIR, "index.html")
        self._assert_element(html, 'id="notes-section"', "notes section")
        self._assert_element(html, 'id="notes-list"', "notes list")
        self._assert_element(html, 'id="note-search-input"', "note search input")
        self._assert_element(html, 'id="note-add-btn"', "note add button")
        self._assert_element(html, 'id="note-export-btn"', "note export button")
        self._assert_element(html, 'id="note-import-input"', "note import input")

    def test_note_modal_in_docs(self):
        html = self._read(DOCS_DIR, "index.html")
        self._assert_element(html, 'id="note-modal"', "note modal overlay")
        self._assert_element(html, 'id="note-edit-title"', "note edit title input")
        self._assert_element(html, 'id="note-edit-content"', "note edit content textarea")
        self._assert_element(html, 'id="note-modal-save"', "note modal save button")
        self._assert_element(html, 'id="note-modal-cancel"', "note modal cancel button")

    def test_due_date_in_form(self):
        html = self._read(DOCS_DIR, "index.html")
        self._assert_element(html, 'id="due-date"', "due date input in add form")
        self.assertIn('type="date"', html, "date input type")

    def test_edit_button_in_card_css(self):
        html = self._read(DOCS_DIR, "index.html")
        self.assertIn(".edit-btn", html, "edit button CSS")

    def test_modal_css(self):
        html = self._read(DOCS_DIR, "index.html")
        self.assertIn(".modal-overlay", html, "modal overlay CSS")
        self.assertIn(".modal-sheet", html, "modal sheet CSS")
        self.assertIn("slide-up", html, "slide-up animation")


class TestPwaJsFunctions(unittest.TestCase):
    """Verify the JS file contains required functions."""

    def _read(self, folder: Path) -> str:
        return (folder / "app.js").read_text(encoding="utf-8")

    def test_edit_functions_in_docs(self):
        js = self._read(DOCS_DIR)
        self.assertIn("function openEditModal(", js, "openEditModal function")
        self.assertIn("function closeEditModal(", js, "closeEditModal function")
        self.assertIn("function saveEditModal(", js, "saveEditModal function")
        self.assertIn("async function updateTodo(", js, "updateTodo function")

    def test_filter_functions_in_docs(self):
        js = self._read(DOCS_DIR)
        self.assertIn("function setFilter(", js, "setFilter function")
        self.assertIn("function setSearch(", js, "setSearch function")
        self.assertIn("function getFilteredTodos(", js, "getFilteredTodos function")

    def test_due_date_formatting_in_docs(self):
        js = self._read(DOCS_DIR)
        self.assertIn("function formatDueDate(", js, "formatDueDate function")
        self.assertIn("已过期", js, "overdue text")
        self.assertIn("今天截止", js, "today due text")
        self.assertIn("明天截止", js, "tomorrow due text")

    def test_search_debounce_in_docs(self):
        js = self._read(DOCS_DIR)
        self.assertIn("debounce", js, "search debounce logic")
        self.assertIn("200", js, "200ms debounce delay")

    def test_offline_detection_in_docs(self):
        js = self._read(DOCS_DIR)
        self.assertIn("navigator.onLine", js, "online status check")
        self.assertIn("goOffline", js, "offline handler")
        self.assertIn("goOnline", js, "online handler")
        self.assertIn("startPolling", js, "polling start")
        self.assertIn("stopPolling", js, "polling stop")

    def test_notes_crud_functions_in_docs(self):
        js = self._read(DOCS_DIR)
        self.assertIn("async function loadNotes(", js, "loadNotes function")
        self.assertIn("async function addNote(", js, "addNote function")
        self.assertIn("async function updateNote(", js, "updateNote function")
        self.assertIn("async function deleteNote(", js, "deleteNote function")

    def test_notes_rendering_in_docs(self):
        js = self._read(DOCS_DIR)
        self.assertIn("function renderNotes(", js, "renderNotes function")
        self.assertIn("function noteCard(", js, "noteCard function")
        self.assertIn("function getFilteredNotes(", js, "getFilteredNotes function")

    def test_notes_export_import_in_docs(self):
        js = self._read(DOCS_DIR)
        self.assertIn("function exportNotes(", js, "exportNotes function")
        self.assertIn("function importNotes(", js, "importNotes function")
        self.assertIn("application/json", js, "JSON export mime type")

    def test_notes_modal_functions_in_docs(self):
        js = self._read(DOCS_DIR)
        self.assertIn("function openNoteEditModal(", js, "openNoteEditModal function")
        self.assertIn("function closeNoteEditModal(", js, "closeNoteEditModal function")
        self.assertIn("function saveNoteEditModal(", js, "saveNoteEditModal function")
        self.assertIn("function openNoteAddModal(", js, "openNoteAddModal function")

    def test_section_switching_in_docs(self):
        js = self._read(DOCS_DIR)
        self.assertIn("function switchSection(", js, "switchSection function")
        self.assertIn('currentSection', js, "currentSection state")

    def test_notes_table_in_api_call(self):
        js = self._read(DOCS_DIR)
        self.assertIn("table", js, "table parameter in apiCall")


if __name__ == "__main__":
    unittest.main()
