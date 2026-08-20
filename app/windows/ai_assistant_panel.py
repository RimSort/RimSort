from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.ai.chat_store import ChatStore
from app.ai.gemini_models import (
    GEMINI_MODELS,
    is_quota_error_message,
    normalize_model_id,
    suggest_models_excluding,
)
from app.ai.gemini_provider import GeminiProvider
from app.ai.tools import mod_context
from app.ai.tools.mod_tools import (
    GEMINI_MOD_TOOL_DECLARATIONS,
    ModToolExecutor,
)
from app.controllers.metadata_controller import MetadataController
from app.models.settings import Settings
from app.utils.app_info import AppInfo


class _CompletionWorker(QThread):
    finished_ok = Signal(str)
    finished_error = Signal(str)

    def __init__(
        self,
        provider: GeminiProvider,
        messages: list[dict[str, str]],
        tool_executor: ModToolExecutor,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._messages = messages
        self._tool_executor = tool_executor

    def run(self) -> None:
        try:
            text = self._provider.complete(
                self._messages,
                tools=GEMINI_MOD_TOOL_DECLARATIONS,
                tool_executor=self._tool_executor,
            )
            self.finished_ok.emit(text)
        except Exception as exc:  # noqa: BLE001
            self.finished_error.emit(str(exc))


class AiAssistantPanel(QDialog):
    _LOADING_INTERVAL_MS = 400
    _MESSAGE_SEPARATOR = "==========================="

    def __init__(
        self,
        settings: Settings,
        metadata_controller: MetadataController,
        get_active_paths: Callable[[], list[str]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.metadata_controller = metadata_controller
        self._get_active_paths = get_active_paths
        self._store = ChatStore()
        self._worker: _CompletionWorker | None = None
        self._loading_dot_count = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._tick_loading)
        self.setWindowTitle(self.tr("AI Assistant"))
        self.setMinimumSize(520, 420)
        self._build_ui()
        self._render_history()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("Provider:")))
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Gemini", "gemini")
        top.addWidget(self.provider_combo)
        top.addWidget(QLabel(self.tr("Model:")))
        self.model_combo = QComboBox()
        for spec in GEMINI_MODELS:
            limit_bits: list[str] = []
            if spec.rpm is not None:
                limit_bits.append(f"{spec.rpm} RPM")
            if spec.rpd is not None:
                limit_bits.append(f"{spec.rpd} RPD")
            limits = f" ({', '.join(limit_bits)})" if limit_bits else ""
            self.model_combo.addItem(f"{spec.label}{limits}", spec.model_id)
        saved_model = normalize_model_id(self.settings.ai_model)
        model_index = self.model_combo.findData(saved_model)
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)
        top.addWidget(self.model_combo)
        top.addWidget(QLabel(self.tr("API key:")))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setText(self.settings.ai_api_key)
        top.addWidget(self.api_key_edit)
        layout.addLayout(top)

        proxy_row = QHBoxLayout()
        proxy_row.addWidget(QLabel(self.tr("Proxy:")))
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText(
            self.tr("host:port, user:pass@host:port, login:pass:host:port")
        )
        self.proxy_edit.setText(self.settings.ai_proxy)
        proxy_row.addWidget(self.proxy_edit)
        layout.addLayout(proxy_row)

        self.history = QTextEdit()
        self.history.setReadOnly(True)
        layout.addWidget(self.history)

        input_row = QHBoxLayout()
        self.clear_btn = QPushButton(self.tr("Clear chat"))
        self.clear_btn.clicked.connect(self._clear_chat)
        input_row.addWidget(self.clear_btn)
        self.input_edit = QLineEdit()
        self.input_edit.returnPressed.connect(self._send)
        input_row.addWidget(self.input_edit)
        self.send_btn = QPushButton(self.tr("Send"))
        self.send_btn.clicked.connect(self._send)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

    def _role_label(self, role: str) -> str:
        if role == "assistant":
            return self.tr("Assistant")
        return self.tr("User")

    def _format_message_line(self, msg: dict[str, str]) -> str:
        timestamp = msg.get("timestamp", "")
        prefix = f"[{timestamp}] " if timestamp else ""
        return f"{prefix}{self._role_label(msg['role'])}: {msg['content']}"

    def _render_history(self, *, loading_text: str | None = None) -> None:
        parts: list[str] = []
        for msg in self._store.as_list():
            parts.append(self._format_message_line(msg))
            parts.append(self._MESSAGE_SEPARATOR)
        if loading_text:
            parts.append(loading_text)
        self.history.setPlainText("\n\n".join(parts))
        scrollbar = self.history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _loading_text(self) -> str:
        dots = "." * self._loading_dot_count
        return self.tr("Loading{dots}").format(dots=dots)

    def _start_loading(self) -> None:
        self._loading_dot_count = 1
        self._render_history(loading_text=self._loading_text())
        self._loading_timer.start(self._LOADING_INTERVAL_MS)

    def _stop_loading(self) -> None:
        self._loading_timer.stop()

    def _tick_loading(self) -> None:
        self._loading_dot_count = (self._loading_dot_count % 3) + 1
        self._render_history(loading_text=self._loading_text())

    def _clear_chat(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._store.clear()
        self._render_history()

    def _current_model_id(self) -> str:
        return normalize_model_id(self.model_combo.currentData())

    def _persist_ai_credentials(self) -> None:
        self.settings.ai_api_key = self.api_key_edit.text().strip()
        self.settings.ai_proxy = self.proxy_edit.text().strip()
        self.settings.ai_model = self._current_model_id()
        self.settings.save()

    def _select_model(self, model_id: str) -> None:
        index = self.model_combo.findData(model_id)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        self.settings.ai_model = normalize_model_id(model_id)
        self.settings.save()

    def _system_context(self) -> str:
        version = AppInfo().app_version
        game_version = self.metadata_controller.game_version
        active_paths = self._get_active_paths()
        active_mods = mod_context.list_active_mods(
            self.metadata_controller, active_paths
        )
        mods_preview = mod_context.format_active_mods_context(
            self.metadata_controller, active_paths, limit=200
        )
        return (
            f"You are a helpful assistant for RimSort {version}. "
            f"RimWorld version: {game_version}. Active mods: {len(active_mods)}. "
            "Answer questions about mod lists. Read-only changes are not applied directly; "
            "use queue_sort_mods, queue_save_mods, queue_download, or queue_run_game only "
            "when the user explicitly asks and RimSort GUI is running. "
            "Do not use Markdown. Reply in plain text only (no **, ##, ```, or bullet lists). "
            "Tools: describe_mod, search_installed_mods, search_workshop_mods, "
            "list_missing_deps, get_instance_summary, "
            "read_log (source player or rimsort), list_active_mods, list_installed_mods.\n\n"
            f"{mods_preview}"
        )

    def _send(self) -> None:
        text = self.input_edit.text().strip()
        if not text or (self._worker and self._worker.isRunning()):
            return
        self._persist_ai_credentials()
        self.input_edit.clear()
        self._store.append("user", text)
        self._start_loading()

        messages = [{"role": "system", "content": self._system_context()}]
        messages.extend(self._store.as_list())
        provider = GeminiProvider(
            self.settings.ai_api_key,
            proxy=self.settings.ai_proxy,
            model=self._current_model_id(),
        )
        tool_executor = ModToolExecutor()
        self.send_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self._worker = _CompletionWorker(provider, messages, tool_executor)
        self._worker.finished_ok.connect(self._on_response)
        self._worker.finished_error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self) -> None:
        self._stop_loading()
        self.send_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)

    def _on_response(self, text: str) -> None:
        self._store.append("assistant", text)
        self._store.save()
        self._render_history()

    def _on_error(self, message: str) -> None:
        self._stop_loading()
        self._render_history()
        timestamp = datetime.now().strftime("%H:%M:%S")  # noqa: DTZ005
        error_block = f"[{timestamp}] {self.tr('Error')}: {message}"
        current = self.history.toPlainText()
        suffix = f"\n\n{error_block}\n\n{self._MESSAGE_SEPARATOR}"
        self.history.setPlainText(f"{current}{suffix}" if current else error_block)
        scrollbar = self.history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        if is_quota_error_message(message):
            suggestions = suggest_models_excluding(self._current_model_id())
            if not suggestions:
                return
            recommended = suggestions[0]
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle(self.tr("Model quota exceeded"))
            dialog.setText(message)
            switch_label = self.tr("Switch to {name}").format(name=recommended.label)
            switch_btn = dialog.addButton(
                switch_label, QMessageBox.ButtonRole.AcceptRole
            )
            dialog.addButton(QMessageBox.StandardButton.Close)
            dialog.exec()
            if dialog.clickedButton() == switch_btn:
                self._select_model(recommended.model_id)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._persist_ai_credentials()
        super().closeEvent(event)

    def show_non_modal(self) -> None:
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.show()
