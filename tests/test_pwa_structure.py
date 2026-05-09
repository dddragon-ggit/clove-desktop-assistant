"""Tests for PWA HTML structure and JS function presence."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
MOBILE_DIR = Path(__file__).resolve().parent.parent / "mobile"


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


class TestDocsMobileSync(unittest.TestCase):
    """Verify docs/ and mobile/ have identical HTML and JS."""

    def test_html_identical(self):
        docs_html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        mobile_html = (MOBILE_DIR / "index.html").read_text(encoding="utf-8")
        self.assertEqual(docs_html, mobile_html, "index.html differs between docs/ and mobile/")

    def test_js_identical(self):
        docs_js = (DOCS_DIR / "app.js").read_text(encoding="utf-8")
        mobile_js = (MOBILE_DIR / "app.js").read_text(encoding="utf-8")
        self.assertEqual(docs_js, mobile_js, "app.js differs between docs/ and mobile/")

    def test_sw_identical(self):
        docs_sw = (DOCS_DIR / "sw.js").read_text(encoding="utf-8")
        mobile_sw = (MOBILE_DIR / "sw.js").read_text(encoding="utf-8")
        self.assertEqual(docs_sw, mobile_sw, "sw.js differs between docs/ and mobile/")

    def test_manifest_identical(self):
        docs_m = (DOCS_DIR / "manifest.json").read_text(encoding="utf-8")
        mobile_m = (MOBILE_DIR / "manifest.json").read_text(encoding="utf-8")
        self.assertEqual(docs_m, mobile_m, "manifest.json differs between docs/ and mobile/")


if __name__ == "__main__":
    unittest.main()
