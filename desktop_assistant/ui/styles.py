from __future__ import annotations


ASSISTANT_STYLES = """
QFrame#assistantRoot {
    background: #f6f8ff;
    border: 1px solid #cdd9f6;
    border-radius: 8px;
}
QLabel#title {
    color: #24304f;
    font-size: 18px;
    font-weight: 700;
}
QLabel#subtitle, QLabel#traceLabel {
    color: #66708f;
    font-size: 12px;
}
QLabel#statusBadge, QLabel#riskBadge, QLabel#capabilityBadge {
    background: #edf7f4;
    color: #245d50;
    border: 1px solid #b7d8cf;
    border-radius: 6px;
    padding: 5px 8px;
    font-weight: 600;
}
QLabel#riskBadge {
    background: #fff2df;
    color: #7a4b18;
    border-color: #ecc681;
}
QLabel#capabilityBadge {
    background: #eef3ff;
    color: #495470;
    border-color: #c8d6f2;
}
QLabel#summaryLabel {
    color: #2b344e;
    background: #ffffff;
    border: 1px solid #dce5f5;
    border-radius: 6px;
    padding: 10px;
}
QFrame#detailPanel, QFrame#confirmationPanel {
    background: #ffffff;
    border: 1px solid #dce5f5;
    border-radius: 6px;
}
QFrame#splitterSection {
    background: transparent;
    border: 0;
}
QSplitter::handle {
    background: transparent;
}
QSplitter::handle:vertical {
    height: 6px;
    margin: 0;
}
QSplitter::handle:horizontal {
    width: 6px;
    margin: 0;
}
QSplitter::handle:vertical:hover {
    background: #cdd9f6;
    border-top: 1px solid #b8c8eb;
    border-bottom: 1px solid #f3f6ff;
}
QSplitter::handle:horizontal:hover {
    background: #cdd9f6;
    border-left: 1px solid #b8c8eb;
    border-right: 1px solid #f3f6ff;
}
QSplitter::handle:vertical:pressed, QSplitter::handle:horizontal:pressed {
    background: #9eb2dd;
}
QLabel#panelTitle {
    color: #5a6381;
    font-size: 12px;
    font-weight: 700;
}
QLabel#panelValue, QLabel#confirmationLabel {
    color: #262f49;
    font-size: 12px;
}
QLineEdit#requestInput, QLineEdit#capabilityDescriptionInput,
QLineEdit#projectNameInput, QLineEdit#projectPathInput, QLineEdit#projectDescriptionInput,
QComboBox#backendCombo, QComboBox#capabilityModeCombo, QComboBox#capabilityRiskCombo,
QComboBox#projectKindCombo {
    background: #ffffff;
    color: #202a45;
    border: 1px solid #cbd8f1;
    border-radius: 6px;
    padding: 8px 10px;
}
QTableWidget#actionTable {
    background: #ffffff;
    color: #202a45;
    border: 1px solid #d8e2f4;
    border-radius: 6px;
    gridline-color: #e8edf8;
    selection-background-color: #e7eefc;
    selection-color: #202a45;
}
QTableWidget#recipeActionTable, QTableWidget#windowTable {
    background: #ffffff;
    color: #202a45;
    border: 1px solid #d8e2f4;
    border-radius: 6px;
    gridline-color: #e8edf8;
    selection-background-color: #e7eefc;
    selection-color: #202a45;
}
QListWidget#recentList, QListWidget#debugList, QListWidget#recoveryList, QListWidget#capabilityList,
QListWidget#whitelistList, QListWidget#recipeList, QListWidget#projectList {
    background: #ffffff;
    color: #202a45;
    border: 1px solid #d8e2f4;
    border-radius: 6px;
    padding: 4px;
}
QListWidget#recentList::item, QListWidget#debugList::item, QListWidget#recoveryList::item, QListWidget#capabilityList::item,
QListWidget#whitelistList::item, QListWidget#recipeList::item, QListWidget#projectList::item {
    padding: 5px 6px;
}
QListWidget#recentList::item:selected, QListWidget#debugList::item:selected,
QListWidget#recoveryList::item:selected,
QListWidget#capabilityList::item:selected, QListWidget#whitelistList::item:selected,
QListWidget#recipeList::item:selected,
QListWidget#projectList::item:selected {
    background: #e7eefc;
    color: #202a45;
}
QHeaderView::section {
    background: #edf3ff;
    color: #4b5674;
    border: 0;
    border-bottom: 1px solid #d8e2f4;
    padding: 6px;
    font-weight: 700;
}
QTextEdit#issuesText, QTextEdit#debugSnapshotText {
    background: #ffffff;
    color: #202a45;
    border: 1px solid #d8e2f4;
    border-radius: 6px;
    padding: 10px;
    selection-background-color: #7e8fbe;
}
QPushButton {
    border-radius: 6px;
    padding: 8px 11px;
    font-weight: 600;
}
QPushButton#primaryButton {
    background: #5c6fa8;
    color: #ffffff;
    border: 1px solid #46588e;
}
QPushButton#secondaryButton {
    background: #edf3ff;
    color: #2b344e;
    border: 1px solid #cbd8f1;
}
QPushButton#dangerButton {
    background: #fae8ef;
    color: #8b294d;
    border: 1px solid #e3b5c8;
}
QPushButton:disabled {
    background: #dfe5ef;
    color: #7d879d;
    border: 1px solid #cfd7e5;
}
"""
