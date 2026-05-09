from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from . import shell_text as text
from .shell_page_helpers import centered_title, page_header, shell_button


def build_provider_page(window: QWidget) -> QWidget:
    """Build the model provider settings page."""
    from ..config import ProviderConfigStore

    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 14, 24, 4)
    layout.setSpacing(12)
    layout.addLayout(page_header(text.PROVIDER_TITLE, window._show_menu))

    form = QFormLayout()
    form.setSpacing(8)

    window._provider_name_input = QLineEdit()
    window._provider_name_input.setPlaceholderText(text.PROVIDER_NAME_PLACEHOLDER)
    form.addRow("名称", window._provider_name_input)

    window._provider_url_input = QLineEdit()
    window._provider_url_input.setPlaceholderText(text.PROVIDER_BASE_URL_PLACEHOLDER)
    form.addRow("地址", window._provider_url_input)

    window._provider_key_input = QLineEdit()
    window._provider_key_input.setPlaceholderText(text.PROVIDER_API_KEY_PLACEHOLDER)
    window._provider_key_input.setEchoMode(QLineEdit.EchoMode.Password)
    form.addRow("密钥", window._provider_key_input)

    window._provider_model_input = QLineEdit()
    window._provider_model_input.setPlaceholderText(text.PROVIDER_MODEL_PLACEHOLDER)
    form.addRow("主模型", window._provider_model_input)

    window._provider_review_input = QLineEdit()
    window._provider_review_input.setPlaceholderText(text.PROVIDER_REVIEW_MODEL_PLACEHOLDER)
    form.addRow("审查模型", window._provider_review_input)

    window._provider_wire_combo = QComboBox()
    window._provider_wire_combo.addItem(text.PROVIDER_WIRE_API_RESPONSES, "responses")
    window._provider_wire_combo.addItem(text.PROVIDER_WIRE_API_ANTHROPIC, "anthropic")
    form.addRow(text.PROVIDER_WIRE_API_LABEL, window._provider_wire_combo)

    layout.addLayout(form)

    window._provider_status_label = QLabel("")
    window._provider_status_label.setObjectName("smallNote")
    window._provider_status_label.setWordWrap(True)
    layout.addWidget(window._provider_status_label)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    auto_btn = shell_button(text.PROVIDER_AUTO_DETECT, window._provider_auto_detect, "shellButton")
    window._provider_auto_detect_btn_ref = auto_btn
    btn_row.addWidget(auto_btn)
    test_btn = shell_button(text.PROVIDER_TEST, window._provider_test_connection, "shellButton")
    window._provider_test_btn_ref = test_btn
    btn_row.addWidget(test_btn)
    btn_row.addStretch(1)
    btn_row.addWidget(shell_button(text.PROVIDER_SAVE, window._provider_save, "primaryShellButton"))
    layout.addLayout(btn_row)

    layout.addStretch(1)

    # Load current config on page build
    _load_provider_config(window)
    return page


def _load_provider_config(window: QWidget) -> None:
    from ..config import ProviderConfigStore

    store = ProviderConfigStore()
    if not store.exists():
        return
    try:
        config = store.load()
    except (ValueError, KeyError):
        return
    window._provider_name_input.setText(config.provider_name)
    window._provider_url_input.setText(config.base_url)
    window._provider_key_input.setText(config.api_key)
    window._provider_model_input.setText(config.model)
    window._provider_review_input.setText(config.review_model)
    idx = window._provider_wire_combo.findData(config.wire_api)
    if idx >= 0:
        window._provider_wire_combo.setCurrentIndex(idx)


class _ProbeWorker(QThread):
    """Background thread for provider probe/auto-detect."""

    finished = Signal(dict)

    def __init__(self, config, *, auto_detect: bool = False) -> None:
        super().__init__()
        self.config = config
        self.auto_detect = auto_detect

    def run(self) -> None:
        from ..adapters.provider_factory import auto_detect_wire_api, probe_provider

        if self.auto_detect:
            wire_api = auto_detect_wire_api(self.config)
            self.finished.emit({"wire_api": wire_api})
        else:
            result = probe_provider(self.config)
            self.finished.emit(result)


def _provider_save(window: QWidget) -> None:
    from ..config import ModelProviderConfig, ProviderConfigStore

    name = window._provider_name_input.text().strip() or "OpenAI"
    url = window._provider_url_input.text().strip()
    key = window._provider_key_input.text().strip()
    model = window._provider_model_input.text().strip()
    review = window._provider_review_input.text().strip() or model
    wire_api = window._provider_wire_combo.currentData()

    if not url or not key or not model:
        window._provider_status_label.setText(text.PROVIDER_SAVE_FAILED.format(error="地址、密钥和模型不能为空"))
        return

    config = ModelProviderConfig(
        provider_name=name,
        base_url=url,
        wire_api=wire_api,
        model=model,
        review_model=review,
        api_key=key,
    )
    try:
        ProviderConfigStore().save(config)
        window._provider_status_label.setText(text.PROVIDER_SAVED)
    except Exception as exc:
        window._provider_status_label.setText(text.PROVIDER_SAVE_FAILED.format(error=str(exc)))


def _provider_auto_detect(window: QWidget) -> None:
    from ..config import ModelProviderConfig

    url = window._provider_url_input.text().strip()
    key = window._provider_key_input.text().strip()
    model = window._provider_model_input.text().strip()
    if not url or not key or not model:
        window._provider_status_label.setText("请先填写地址、密钥和模型")
        return

    config = ModelProviderConfig(
        base_url=url,
        api_key=key,
        model=model,
        review_model=model,
    )
    window._provider_status_label.setText("正在检测...")
    window._provider_auto_detect_btn_ref.setEnabled(False)

    worker = _ProbeWorker(config, auto_detect=True)
    worker.finished.connect(lambda result: _on_auto_detect_done(window, result))
    worker.start()
    window._probe_worker = worker  # prevent GC


def _on_auto_detect_done(window: QWidget, result: dict) -> None:
    window._provider_auto_detect_btn_ref.setEnabled(True)
    wire_api = result.get("wire_api", "responses")
    idx = window._provider_wire_combo.findData(wire_api)
    if idx >= 0:
        window._provider_wire_combo.setCurrentIndex(idx)
    label = text.PROVIDER_WIRE_API_ANTHROPIC if wire_api == "anthropic" else text.PROVIDER_WIRE_API_RESPONSES
    window._provider_status_label.setText(f"检测完成，已选择：{label}")


def _provider_test_connection(window: QWidget) -> None:
    from ..config import ModelProviderConfig

    url = window._provider_url_input.text().strip()
    key = window._provider_key_input.text().strip()
    model = window._provider_model_input.text().strip()
    if not url or not key or not model:
        window._provider_status_label.setText("请先填写地址、密钥和模型")
        return

    wire_api = window._provider_wire_combo.currentData()
    config = ModelProviderConfig(
        base_url=url,
        api_key=key,
        model=model,
        review_model=model,
        wire_api=wire_api,
    )
    window._provider_status_label.setText("正在测试...")
    window._provider_test_btn_ref.setEnabled(False)

    worker = _ProbeWorker(config, auto_detect=False)
    worker.finished.connect(lambda result: _on_test_done(window, result))
    worker.start()
    window._probe_worker = worker  # prevent GC


def _on_test_done(window: QWidget, result: dict) -> None:
    window._provider_test_btn_ref.setEnabled(True)
    if result.get("ok"):
        wire_api = result.get("wire_api", "unknown")
        window._provider_status_label.setText(text.PROVIDER_TEST_OK.format(wire_api=wire_api))
    else:
        details = result.get("details", {})
        errors = "; ".join(f"{k}: {v}" for k, v in details.items())
        window._provider_status_label.setText(text.PROVIDER_TEST_FAIL.format(error=errors or "未知错误"))
