from __future__ import annotations


def shell_style(color: str, *, orb: bool = False) -> str:
    r, g, b = _hex_to_rgb(color)
    if orb:
        return """
QMainWindow {
    background: transparent;
    border: 0;
}
QWidget {
    background: transparent;
    border: 0;
}
QFrame#shellRoot {
    background: transparent;
    border: none;
    border-radius: 39px;
}
"""
    radius = 18
    alpha = 252
    glow_r, glow_g, glow_b = _mix((r, g, b), (247, 177, 220), 0.24)
    soft_r, soft_g, soft_b = _mix((r, g, b), (180, 211, 255), 0.34)
    return BASE_STYLE + f"""
QFrame#shellRoot {{
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 rgba(37, 46, 72, {alpha}),
        stop: 0.42 rgba(72, 83, 119, {alpha}),
        stop: 0.74 rgba(116, 87, 128, {alpha}),
        stop: 1 rgba(52, 59, 89, {alpha})
    );
    border: 1px solid rgba({soft_r}, {soft_g}, {soft_b}, 190);
    border-radius: {radius}px;
}}
QFrame#shellSurface {{
    border-color: rgba({glow_r}, {glow_g}, {glow_b}, 126);
}}
QLabel#pageTitle {{
    color: rgba({soft_r}, {soft_g}, {soft_b}, 246);
}}
QLabel#sectionLabel {{
    color: rgba({glow_r}, {glow_g}, {glow_b}, 235);
}}
QLineEdit#predictionInput:focus, QLineEdit#todoQuickInput:focus,
QLineEdit#todoInput:focus, QLineEdit#todoDescriptionInput:focus,
QLineEdit#todoTimeInput:focus, QLineEdit#workspaceInput:focus,
QLineEdit#feedbackInput:focus, QComboBox#workspaceActionTargetInput:focus,
QComboBox#workspaceRecipeCombo:focus {{
    border: 1px solid rgba({soft_r}, {soft_g}, {soft_b}, 210);
    background: rgba(255, 255, 255, 48);
}}
QPushButton#navButton:hover, QPushButton#primaryShellButton:hover {{
    background: rgba({glow_r}, {glow_g}, {glow_b}, 74);
    border-color: rgba({soft_r}, {soft_g}, {soft_b}, 190);
}}
QPushButton#secondaryShellButton:hover, QPushButton#iconButton:hover {{
    background: rgba({soft_r}, {soft_g}, {soft_b}, 54);
    border-color: rgba({soft_r}, {soft_g}, {soft_b}, 170);
}}
QListWidget#todoList::item:selected, QListWidget#workspaceActionList::item:selected {{
    background: rgba({soft_r}, {soft_g}, {soft_b}, 72);
    border-left: 3px solid rgba({glow_r}, {glow_g}, {glow_b}, 210);
}}
"""


BASE_STYLE = """
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI";
    color: #ffffff;
}
QFrame#shellRoot {
    color: #ffffff;
}
QLabel#heroGreeting {
    font-size: 27px;
    font-weight: 800;
    color: #f9fbff;
}
QLabel#heroCount {
    font-size: 14px;
    color: rgba(232, 241, 255, 226);
}
QLabel#heroNext, QLabel#smallNote, QCheckBox#smallNote {
    font-size: 12px;
    color: rgba(223, 232, 248, 196);
}
QLabel#pageTitle {
    font-size: 16px;
    font-weight: 800;
}
QFrame#pageAccent {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 0, y2: 1,
        stop: 0 #b4d3ff,
        stop: 1 #f7b1dc
    );
    border-radius: 2px;
}
QLabel#sectionLabel {
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0px;
}
QFrame#shellSurface {
    background: rgba(250, 247, 255, 28);
    border: 1px solid rgba(255, 255, 255, 66);
    border-radius: 10px;
}
QPushButton#iconButton {
    background: rgba(245, 250, 255, 36);
    border: 1px solid rgba(215, 226, 255, 72);
    border-radius: 9px;
    padding: 3px 8px;
    font-weight: 800;
}
QPushButton#navButton {
    background: rgba(248, 241, 255, 40);
    border: 1px solid rgba(221, 233, 255, 86);
    border-radius: 14px;
    min-height: 44px;
    font-size: 14px;
    font-weight: 800;
    text-align: center;
    margin: 1px 0;
}
QPushButton#primaryShellButton, QPushButton#secondaryShellButton {
    background: rgba(247, 177, 220, 54);
    border: 1px solid rgba(239, 191, 230, 120);
    border-radius: 9px;
    padding: 8px 10px;
    font-weight: 800;
}
QPushButton#secondaryShellButton {
    background: rgba(180, 211, 255, 30);
    border-color: rgba(206, 222, 255, 88);
}
QPushButton:disabled {
    color: rgba(224, 232, 244, 118);
    background: rgba(255, 255, 255, 18);
    border-color: rgba(255, 255, 255, 36);
}
QLineEdit#predictionInput, QLineEdit#todoQuickInput, QLineEdit#todoInput, QLineEdit#todoDescriptionInput, QLineEdit#todoTimeInput,
QLineEdit#workspaceInput, QLineEdit#feedbackInput {
    background: rgba(255, 255, 255, 34);
    border: 1px solid rgba(221, 233, 255, 76);
    border-radius: 9px;
    padding: 9px 12px;
    selection-background-color: rgba(255, 255, 255, 80);
}
QLineEdit#predictionInput::placeholder {
    color: rgba(255, 255, 255, 145);
}
QListWidget#todoList, QListWidget#workspaceActionList {
    background: rgba(20, 26, 44, 54);
    border: 1px solid rgba(221, 233, 255, 58);
    border-radius: 9px;
    padding: 6px;
}
QListWidget#todoList::item, QListWidget#workspaceActionList::item {
    padding: 8px 8px;
    border-radius: 7px;
}
QListWidget#todoList::item:selected, QListWidget#workspaceActionList::item:selected {
    background: rgba(180, 211, 255, 64);
}
QTextEdit#workspaceText, QTextEdit#chatText, QTextEdit#todoDetail, QTextEdit#workspaceConfirmText {
    background: rgba(17, 23, 39, 58);
    border: 1px solid rgba(221, 233, 255, 58);
    border-radius: 9px;
    padding: 10px;
    selection-background-color: rgba(247, 177, 220, 92);
}
QScrollArea#todoDetailScroll, QWidget#todoDetailContent {
    background: transparent;
    border: none;
}
QComboBox#backendCombo, QComboBox#todoPriorityCombo, QComboBox#workspaceActionTypeCombo,
QComboBox#workspaceActionTargetInput, QComboBox#workspaceRecipeCombo {
    background: rgba(255, 255, 255, 34);
    border: 1px solid rgba(221, 233, 255, 76);
    border-radius: 9px;
    padding: 6px 8px;
}
QComboBox QAbstractItemView {
    background: #2f385a;
    color: #f8fbff;
    border: 1px solid rgba(221, 233, 255, 96);
    selection-background-color: #6c7fb2;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 5px;
    border: 1px solid rgba(221, 233, 255, 112);
    background: rgba(255, 255, 255, 26);
}
QCheckBox::indicator:checked {
    background: #f7b1dc;
    border: 1px solid #dceaff;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px 0 2px 0;
}
QScrollBar::handle:vertical {
    background: rgba(221, 233, 255, 88);
    border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QSizeGrip {
    width: 18px;
    height: 18px;
}
"""


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    clean = value.strip().lstrip("#")
    if len(clean) != 6:
        return 46, 125, 91
    return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)


def _mix(left: tuple[int, int, int], right: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    ratio = max(0.0, min(1.0, amount))
    return tuple(round(left[index] * (1 - ratio) + right[index] * ratio) for index in range(3))
