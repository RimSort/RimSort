import html
import json
import math
import re
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

from loguru import logger
from PySide6.QtCore import QEvent, QPoint, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QColor, QFontMetrics, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QToolTip,
    QVBoxLayout,
    QWidget,
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
    summarize_tool_result,
)
from app.controllers.metadata_controller import MetadataController
from app.models.settings import Settings
from app.utils import http
from app.utils.app_info import AppInfo
from app.utils.event_bus import EventBus
from app.utils.generic import open_url_browser
from app.utils.steam.steambrowser.browser import (
    URL_PREFIX_SHAREDFILES,
    parse_publishedfileid_from_url,
)
from app.utils.steam.steambrowser.download_list_widget import ModDownloadListWidget
from app.utils.steam.webapi.wrapper import (
    ISteamRemoteStorage_GetPublishedFileDetails,
    ISteamUser_GetPlayerSummaries,
)

LOCALIZATION_LANGUAGES: list[tuple[str, str]] = [
    ("", "Do not search"),
    ("ru", "RU"),
    ("en", "EN"),
    ("fr", "FR"),
    ("de", "DE"),
    ("es", "ES"),
    ("zh", "ZH"),
    ("ja", "JA"),
    ("pl", "PL"),
    ("pt", "PT"),
]
_MOD_BUTTON_PAGE_SIZE = 5


class _CompletionWorker(QThread):
    finished_ok = Signal(str)
    finished_error = Signal(str)
    tool_trace = Signal(str, dict, dict)
    progress = Signal(int, int, str)

    def __init__(
        self,
        provider: GeminiProvider,
        messages: list[dict[str, str]],
        steam_apikey_override: str | None = None,
    ) -> None:
        super().__init__()
        self._provider = provider
        self._messages = messages
        self._steam_apikey_override = steam_apikey_override

    def _on_tool_call(
        self, name: str, args: dict[str, Any], result: dict[str, Any]
    ) -> None:
        self.tool_trace.emit(name, args, result)

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.emit(current, total, message)

    def run(self) -> None:
        tool_executor = ModToolExecutor(
            steam_apikey_override=self._steam_apikey_override,
            on_progress=self._on_progress,
        )
        try:
            text = self._provider.complete(
                self._messages,
                tools=GEMINI_MOD_TOOL_DECLARATIONS,
                tool_executor=tool_executor,
                on_tool_call=self._on_tool_call,
            )
            self.finished_ok.emit(text)
        except Exception as exc:  # noqa: BLE001
            self.finished_error.emit(str(exc))


class _CompatibilityCheckWorker(QThread):
    """Plain (no tools) LLM call used to sanity-check a download list."""

    finished_ok = Signal(str)
    finished_error = Signal(str)

    def __init__(
        self, provider: GeminiProvider, messages: list[dict[str, str]]
    ) -> None:
        super().__init__()
        self._provider = provider
        self._messages = messages

    def run(self) -> None:
        try:
            text = self._provider.complete(self._messages)
            self.finished_ok.emit(text)
        except Exception as exc:  # noqa: BLE001
            self.finished_error.emit(str(exc))


class _ModTitleWorker(QThread):
    """Resolves a Steam Workshop item title from its publishedfileid."""

    finished_ok = Signal(str, str)  # publishedfileid, title

    def __init__(self, publishedfileid: str) -> None:
        super().__init__()
        self._pfid = publishedfileid

    def run(self) -> None:
        try:
            metadata, _failed, _errors = ISteamRemoteStorage_GetPublishedFileDetails(
                [self._pfid]
            )
        except Exception:  # noqa: BLE001
            metadata = []
        title = str(metadata[0].get("title", self._pfid)) if metadata else self._pfid
        self.finished_ok.emit(self._pfid, title)


class _ModDetailsWorker(QThread):
    """Fetches Steam Workshop details/author/preview image for one mod."""

    finished_ok = Signal(str, str)  # publishedfileid, tooltip html

    def __init__(self, publishedfileid: str, api_key: str, cache_dir: Path) -> None:
        super().__init__()
        self._pfid = publishedfileid
        self._api_key = api_key
        self._cache_dir = cache_dir

    def run(self) -> None:
        tooltip_html = _build_enriched_mod_tooltip(
            self._pfid, self._api_key, self._cache_dir
        )
        self.finished_ok.emit(self._pfid, tooltip_html)


def _build_enriched_mod_tooltip(
    publishedfileid: str, api_key: str, cache_dir: Path
) -> str:
    try:
        metadata, _failed, _errors = ISteamRemoteStorage_GetPublishedFileDetails(
            [publishedfileid]
        )
    except Exception:  # noqa: BLE001
        metadata = []
    if not metadata:
        return html.escape(publishedfileid)

    info = metadata[0]
    title = str(info.get("title", publishedfileid))
    description = str(info.get("file_description", ""))[:400]
    tags = [
        str(tag.get("tag", ""))
        for tag in info.get("tags", [])
        if isinstance(tag, dict) and tag.get("tag")
    ]
    creator = str(info.get("creator", ""))
    author = creator
    if creator:
        try:
            names = ISteamUser_GetPlayerSummaries([creator], api_key)
            author = names.get(creator, creator)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to resolve mod author name for {creator}: {exc}")

    img_html = ""
    preview_url = info.get("preview_url")
    if preview_url:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            img_path = cache_dir / f"{publishedfileid}.jpg"
            if not img_path.exists():
                response = http.get(str(preview_url), timeout=(5, 20))
                response.raise_for_status()
                img_path.write_bytes(response.content)
            img_html = f'<img src="file:///{img_path.as_posix()}" width="220"><br>'
        except Exception:  # noqa: BLE001
            img_html = ""

    tags_line = ", ".join(tags) if tags else "not specified"
    return (
        f"{img_html}<b>{html.escape(title)}</b><br>"
        f"Author: {html.escape(author)}<br>"
        f"Game version tags: {html.escape(tags_line)}<br>"
        f"{html.escape(description)}"
    )


def _brief_tool_args(name: str, args: dict[str, Any]) -> str:
    if args.get("query"):
        return f'"{args["query"]}"'
    if name in ("queue_download", "validate_workshop_ids"):
        pfids = args.get("publishedfileids") or []
        if isinstance(pfids, list):
            return f"{len(pfids)} ids"
    if name == "find_localizations_for_active_mods":
        raw = args.get("package_ids")
        language = args.get("language", "")
        scope = f"{len(raw)} mods" if isinstance(raw, list) and raw else "all active"
        return f"{language}, {scope}" if language else scope
    if args.get("package_id"):
        return str(args["package_id"])
    if args.get("source"):
        return str(args["source"])
    return ""


def _format_tool_trace(name: str, args: dict[str, Any], result: dict[str, Any]) -> str:
    brief = _brief_tool_args(name, args)
    args_part = f"({brief})" if brief else ""
    summary = summarize_tool_result(name, result)
    return f"{name}{args_part} → {summary}"


def _format_tool_tooltip(
    name: str, _args: dict[str, Any], result: dict[str, Any]
) -> str:
    """Full (plain-text) tooltip content shown on hover over a tool trace line."""
    if name in ("search_workshop_mods", "search_steam_workshop"):
        matches = result.get("matches", [])
        if not matches:
            return str(result.get("error") or "No matches")
        return "\n".join(
            f"{m.get('title', '?')} ({m.get('publishedfileid', '?')})"
            for m in matches[:20]
        )
    if name == "find_localizations_for_active_mods":
        suggestions = result.get("suggestions", [])
        if not suggestions:
            errors = result.get("errors") or []
            return "\n".join(str(e) for e in errors) or "No suggestions"
        lines = []
        for s in suggestions:
            recommended = s.get("recommended")
            target = s.get("target_name", "?")
            if recommended:
                lines.append(f"{target} → {recommended.get('title', '?')}")
            else:
                lines.append(f"{target} → (no candidates)")
        return "\n".join(lines)
    if name == "validate_workshop_ids":
        valid = result.get("valid", [])
        invalid = result.get("invalid", [])
        return f"Valid: {', '.join(valid) or '-'}\nInvalid: {', '.join(invalid) or '-'}"
    if name == "queue_download":
        ids = result.get("valid_ids", [])
        return f"Queued: {', '.join(ids) or '-'}"
    try:
        dumped = json.dumps(result, indent=2, ensure_ascii=False)
    except TypeError:
        dumped = str(result)
    return dumped[:1000] + ("…" if len(dumped) > 1000 else "")


_LINK_RE = re.compile(r"\[(.+?)\]\((https?://[^\s()]+)\)|(https?://\S+)")
_URL_LIKE = re.compile(r"^https?://", re.IGNORECASE)
_GENERIC_PREFACE_MARKERS = (
    "ссылке",
    "link",
    "url",
    "http",
    "загрузить",
    "download",
    "following",
)


def _looks_like_url(text: str) -> bool:
    stripped = text.strip()
    return bool(_URL_LIKE.match(stripped) or "steamcommunity.com" in stripped.lower())


def _infer_mod_name_before_url(content: str, url_start: int) -> str | None:
    prefix = content[:url_start].rstrip()
    if not prefix:
        return None
    last_line = prefix.rsplit("\n", maxsplit=1)[-1].strip()
    last_line = re.sub(r"[:：\.…]\s*$", "", last_line).strip()
    if len(last_line) < 3 or _looks_like_url(last_line):
        return None
    lowered = last_line.lower()
    if any(marker in lowered for marker in _GENERIC_PREFACE_MARKERS):
        return None
    return last_line


def _replace_link(match: re.Match[str]) -> str:
    label, url, bare_url = match.group(1), match.group(2), match.group(3)
    if bare_url:
        return f'<a href="{bare_url}">{bare_url}</a>'
    return f'<a href="{url}">{label}</a>'


def _linkify(escaped_html: str) -> str:
    """Turn `[label](url)` and plain URLs in an already-HTML-escaped
    string into clickable <a> tags."""
    return _LINK_RE.sub(_replace_link, escaped_html)


def _extract_mod_links(content: str) -> list[tuple[str, str, str]]:
    """Find Steam Workshop mod links in raw (pre-escape) message content.

    Returns a list of (label, publishedfileid, url), de-duplicated by pfid.
    """
    links: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for match in _LINK_RE.finditer(content):
        label, url, bare_url = match.group(1), match.group(2), match.group(3)
        final_url = url or bare_url
        if not final_url:
            continue
        pfid = parse_publishedfileid_from_url(final_url)
        if not pfid or pfid in seen:
            continue
        seen.add(pfid)
        resolved_label = (label or "").strip()
        if not resolved_label or _looks_like_url(resolved_label):
            inferred = _infer_mod_name_before_url(content, match.start())
            resolved_label = inferred or ""
        links.append((resolved_label, pfid, final_url))
    return links


class AiAssistantPanel(QDialog):
    _LOADING_INTERVAL_MS = 400
    _BUBBLE_MAX_WIDTH = 420
    _BUBBLE_MIN_WIDTH = 120
    _BUBBLE_HORIZONTAL_PADDING = 20
    _BUBBLE_VERTICAL_PADDING = 12
    _USER_BUBBLE_STYLE = (
        "background-color: #2f6feb; color: white; "
        "border-radius: 10px; padding: 6px 10px;"
    )
    _ASSISTANT_BUBBLE_STYLE = (
        "background-color: rgba(127, 127, 127, 60); "
        "border-radius: 10px; padding: 6px 10px;"
    )
    # (background, text) colors used for the selection highlight, since the
    # default system highlight color can blend into a same-toned bubble.
    _USER_SELECTION_COLORS = ("#ffd54f", "#1a1a1a")
    _ASSISTANT_SELECTION_COLORS = ("#2f6feb", "#ffffff")
    _LOCALIZATION_PROGRESS_PREFIXES = (
        "Scanning active mods for existing localizations",
        "Searching Steam Workshop for localizations",
        "Checking:",
        "Workshop search:",
    )

    def __init__(
        self,
        settings: Settings,
        metadata_controller: MetadataController,
        get_active_paths: Callable[[], list[str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.metadata_controller = metadata_controller
        self._get_active_paths = get_active_paths
        self._store = ChatStore()
        self._worker: _CompletionWorker | None = None
        self._compat_worker: _CompatibilityCheckWorker | None = None
        self._detail_workers: list[_ModDetailsWorker] = []
        self._title_workers: list[_ModTitleWorker] = []
        self._title_fetch_pending: set[str] = set()
        self._trace_rows: list[QWidget] = []
        self._mod_titles: dict[str, str] = {}
        self._mod_buttons: dict[str, list[QPushButton]] = {}
        self._mod_tooltip_cache: dict[str, str] = {}
        self._tooltip_fetch_pending: set[str] = set()
        self._progress_current = 0
        self._progress_total = 0
        self._progress_message = ""
        self._loading_dot_count = 0
        self._loading_bubble: QTextBrowser | None = None
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._tick_loading)
        self._sent_history: list[str] = [
            m["content"] for m in self._store.as_list() if m["role"] == "user"
        ]
        self._history_cursor: int | None = None
        self._history_draft = ""
        self.setWindowTitle(self.tr("AI Assistant"))
        self.setMinimumSize(760, 480)
        self._build_ui()
        self._render_history()

    def _build_ui(self) -> None:
        outer_layout = QHBoxLayout(self)

        self._download_list = ModDownloadListWidget(
            title=self.tr("Mod list"),
            show_steamworks_button=False,
            show_add_by_id_button=True,
            url_builder=lambda pfid: f"{URL_PREFIX_SHAREDFILES}{pfid}",
        )
        self._download_list.download_requested.connect(self._on_download_list_requested)
        self._download_list.mod_added.connect(self._on_mod_added)
        self._download_list.mod_removed.connect(self._on_mod_removed)
        outer_layout.addWidget(self._download_list)

        chat_container = QWidget()
        layout = QVBoxLayout(chat_container)
        layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(chat_container, 1)

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

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(self.tr("Search mod localization for language:")))
        self.localization_combo = QComboBox()
        for code, label in LOCALIZATION_LANGUAGES:
            self.localization_combo.addItem(self.tr(label) if not code else label, code)
        lang_index = self.localization_combo.findData(
            self.settings.ai_localization_language
        )
        if lang_index >= 0:
            self.localization_combo.setCurrentIndex(lang_index)
        lang_row.addWidget(self.localization_combo)
        lang_row.addStretch()
        layout.addLayout(lang_row)

        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        history_content = QWidget()
        self._history_layout = QVBoxLayout(history_content)
        self._history_layout.addStretch()
        self.history_scroll.setWidget(history_content)
        layout.addWidget(self.history_scroll)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        input_row = QHBoxLayout()
        self.clear_btn = QPushButton(self.tr("Clear chat"))
        self.clear_btn.clicked.connect(self._clear_chat)
        input_row.addWidget(self.clear_btn)
        self.input_edit = QLineEdit()
        self.input_edit.returnPressed.connect(self._send)
        self.input_edit.installEventFilter(self)
        input_row.addWidget(self.input_edit)
        self.send_btn = QPushButton(self.tr("Send"))
        self.send_btn.clicked.connect(self._send)
        input_row.addWidget(self.send_btn)
        layout.addLayout(input_row)

    def eventFilter(self, watched: Any, event: Any) -> bool:
        if watched is self.input_edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Up:
                self._recall_older_message()
                return True
            if key == Qt.Key.Key_Down:
                self._recall_newer_message()
                return True
        if isinstance(watched, QTextBrowser) and event.type() == QEvent.Type.Wheel:
            # Bubbles are sized to their content and have no internal
            # scrollbar; forward the wheel event to the chat scroll area
            # instead of letting the browser swallow it.
            QApplication.sendEvent(self.history_scroll, event)
            return True
        if isinstance(watched, QTextBrowser) and event.type() == QEvent.Type.ToolTip:
            return self._handle_bubble_tooltip(watched, event)
        return super().eventFilter(watched, event)

    def _handle_bubble_tooltip(self, browser: QTextBrowser, event: Any) -> bool:
        anchor = browser.anchorAt(event.pos())
        pfid = parse_publishedfileid_from_url(anchor) if anchor else None
        if not pfid:
            QToolTip.hideText()
            return False
        tooltip_html = self._mod_tooltip_cache.get(pfid)
        if tooltip_html is None:
            self._queue_mod_tooltip_fetch(pfid)
            tooltip_html = html.escape(self._display_mod_label(pfid))
        QToolTip.showText(event.globalPos(), tooltip_html, browser)
        return True

    def _recall_older_message(self) -> None:
        """Up arrow: step to the previous (older) sent message."""
        if not self._sent_history:
            return
        if self._history_cursor is None:
            self._history_draft = self.input_edit.text()
            self._history_cursor = len(self._sent_history) - 1
        elif self._history_cursor > 0:
            self._history_cursor -= 1
        self._set_input_from_history()

    def _recall_newer_message(self) -> None:
        """Down arrow: step forward toward the newest message, then the draft."""
        if self._history_cursor is None:
            return
        if self._history_cursor >= len(self._sent_history) - 1:
            self._history_cursor = None
            self.input_edit.setText(self._history_draft)
            self.input_edit.setCursorPosition(len(self._history_draft))
            return
        self._history_cursor += 1
        self._set_input_from_history()

    def _set_input_from_history(self) -> None:
        if self._history_cursor is None:
            return
        text = self._sent_history[self._history_cursor]
        self.input_edit.setText(text)
        self.input_edit.setCursorPosition(len(text))

    def _bubble_style(self, role: str) -> str:
        return (
            self._USER_BUBBLE_STYLE if role == "user" else self._ASSISTANT_BUBBLE_STYLE
        )

    def _selection_colors(self, role: str) -> tuple[str, str]:
        return (
            self._USER_SELECTION_COLORS
            if role == "user"
            else self._ASSISTANT_SELECTION_COLORS
        )

    def _resize_bubble(self, bubble: QTextBrowser) -> int:
        """Recompute bubble width/height from its document; return the width."""
        doc = bubble.document()
        content_width_max = self._BUBBLE_MAX_WIDTH - self._BUBBLE_HORIZONTAL_PADDING
        content_width_min = self._BUBBLE_MIN_WIDTH - self._BUBBLE_HORIZONTAL_PADDING
        doc.setTextWidth(content_width_max)
        ideal_width = math.ceil(doc.idealWidth())
        content_width = max(content_width_min, min(content_width_max, ideal_width))
        doc.setTextWidth(content_width)
        doc_height = math.ceil(doc.size().height())
        bubble_width = content_width + self._BUBBLE_HORIZONTAL_PADDING
        bubble.setFixedWidth(bubble_width)
        bubble.setFixedHeight(doc_height + self._BUBBLE_VERTICAL_PADDING + 4)
        bubble.setProperty("bubble_width", bubble_width)
        return bubble_width

    def _set_bubble_html(self, bubble: QTextBrowser, html_text: str) -> int:
        bubble.setHtml(html_text)
        bubble.document().setDocumentMargin(0)
        width = self._resize_bubble(bubble)
        # Recompute after the event loop settles the layout, which fixes
        # clipping that setTextWidth's own layout pass sometimes misses on
        # long paragraphs.
        QTimer.singleShot(0, lambda: self._resize_bubble(bubble))
        return width

    def _make_bubble(self, role: str, html_text: str) -> tuple[QTextBrowser, int]:
        browser = QTextBrowser()
        browser.setFrameShape(QFrame.Shape.NoFrame)
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setOpenLinks(False)
        browser.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        browser.setStyleSheet(
            self._bubble_style(role) + " QTextBrowser { border: none; }"
        )
        selection_bg, selection_fg = self._selection_colors(role)
        palette = browser.palette()
        palette.setColor(QPalette.ColorRole.Highlight, QColor(selection_bg))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(selection_fg))
        browser.setPalette(palette)
        browser.anchorClicked.connect(self._on_bubble_link_clicked)
        browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        browser.customContextMenuRequested.connect(
            partial(self._on_bubble_context_menu, browser)
        )
        browser.installEventFilter(self)
        width = self._set_bubble_html(browser, html_text)
        return browser, width

    def _on_bubble_link_clicked(self, url: QUrl) -> None:
        self._toggle_mod_link(url.toString())

    def _toggle_mod_link(self, url: str) -> None:
        pfid = parse_publishedfileid_from_url(url)
        if not pfid:
            open_url_browser(url)
            return
        if self._download_list.has_mod(pfid):
            self._download_list.remove_mod(pfid)
        else:
            self._download_list.add_mod(pfid, title=self._display_mod_label(pfid))

    def _on_bubble_context_menu(self, browser: QTextBrowser, point: QPoint) -> None:
        anchor = browser.anchorAt(point)
        if not anchor:
            return
        menu = QMenu(self)
        pfid = parse_publishedfileid_from_url(anchor)
        if pfid:
            toggle_label = (
                self.tr("Remove from list")
                if self._download_list.has_mod(pfid)
                else self.tr("Add to list")
            )
            toggle_action = menu.addAction(toggle_label)
            toggle_action.triggered.connect(partial(self._toggle_mod_link, anchor))
            workshop_action = menu.addAction(self.tr("Open in Workshop browser"))
            workshop_action.triggered.connect(
                partial(EventBus().do_browse_workshop_url.emit, anchor)
            )
        browser_action = menu.addAction(self.tr("Open in browser"))
        browser_action.triggered.connect(partial(open_url_browser, anchor))
        menu.exec_(browser.mapToGlobal(point))

    def _make_timestamp_label(self, timestamp: str) -> QLabel:
        label = QLabel(html.escape(timestamp))
        label.setStyleSheet("font-size: 10px; color: gray;")
        return label

    def _add_bubble(
        self,
        role: str,
        html_text: str,
        timestamp: str = "",
        mod_links: list[tuple[str, str, str]] | None = None,
    ) -> QTextBrowser:
        bubble, bubble_width = self._make_bubble(role, html_text)
        timestamp_label = self._make_timestamp_label(timestamp) if timestamp else None
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            row_layout.addStretch()
            if timestamp_label is not None:
                row_layout.addWidget(timestamp_label)
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            if timestamp_label is not None:
                row_layout.addWidget(timestamp_label)
            row_layout.addStretch()
        self._history_layout.insertWidget(self._history_layout.count() - 1, row)
        if mod_links:
            for label, pfid, _url in mod_links:
                self._register_mod_link(pfid, label)
            buttons_row = self._make_mod_link_buttons_row(mod_links, bubble_width)
            self._history_layout.insertWidget(
                self._history_layout.count() - 1, buttons_row
            )
        return bubble

    def _register_mod_link(self, pfid: str, label: str) -> None:
        cleaned = label.strip()
        if cleaned and not _looks_like_url(cleaned):
            self._mod_titles[pfid] = cleaned
            return
        existing = self._mod_titles.get(pfid, "")
        if existing and not _looks_like_url(existing):
            return
        self._mod_titles[pfid] = pfid
        self._queue_mod_title_fetch(pfid)

    def _display_mod_label(self, pfid: str) -> str:
        title = self._mod_titles.get(pfid, pfid)
        if _looks_like_url(title):
            return pfid
        return title

    def _elided_mod_label(
        self,
        pfid: str,
        *,
        button: QPushButton | None = None,
        width: int | None = None,
    ) -> str:
        label = self._display_mod_label(pfid)
        font = button.font() if button is not None else self.font()
        metrics = QFontMetrics(font)
        prefix_width = metrics.horizontalAdvance("+ ")
        if width is None:
            stored = button.property("bubble_width") if button is not None else None
            width = stored if isinstance(stored, int) else self._BUBBLE_MAX_WIDTH
        max_width = width - prefix_width - 16
        return metrics.elidedText(label, Qt.TextElideMode.ElideRight, max_width)

    def _queue_mod_title_fetch(self, pfid: str) -> None:
        if pfid in self._title_fetch_pending:
            return
        self._title_fetch_pending.add(pfid)
        worker = _ModTitleWorker(pfid)
        worker.finished_ok.connect(self._on_mod_title_ready)
        worker.finished.connect(partial(self._title_workers.remove, worker))
        self._title_workers.append(worker)
        worker.start()

    def _on_mod_title_ready(self, pfid: str, title: str) -> None:
        self._title_fetch_pending.discard(pfid)
        if _looks_like_url(title):
            return
        self._mod_titles[pfid] = title
        self._refresh_mod_buttons_style()
        if self._download_list.has_mod(pfid):
            self._download_list.set_item_title(pfid, title)

    def _make_mod_toggle_button(self, pfid: str, width: int) -> QPushButton:
        added = self._download_list.has_mod(pfid)
        button = QPushButton(
            ("✓ " if added else "+ ") + self._elided_mod_label(pfid, width=width)
        )
        button.setProperty("mod_pfid", pfid)
        button.setProperty("bubble_width", width)
        button.setFlat(True)
        button.setMinimumWidth(width)
        button.setMaximumWidth(width)
        button.clicked.connect(partial(self._toggle_mod_link_by_pfid, pfid))
        self._mod_buttons.setdefault(pfid, []).append(button)
        return button

    def _toggle_mod_link_by_pfid(self, pfid: str) -> None:
        if self._download_list.has_mod(pfid):
            self._download_list.remove_mod(pfid)
        else:
            self._download_list.add_mod(pfid, title=self._display_mod_label(pfid))

    def _make_mod_link_buttons_row(
        self, links: list[tuple[str, str, str]], bubble_width: int
    ) -> QWidget:
        outer = QWidget()
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        column = QWidget()
        column.setFixedWidth(bubble_width)
        row_layout = QVBoxLayout(column)
        row_layout.setContentsMargins(0, 2, 0, 6)
        row_layout.setSpacing(4)
        outer_layout.addWidget(column)
        outer_layout.addStretch()
        state = {"shown": 0}

        def render_page() -> None:
            while row_layout.count():
                item = row_layout.takeAt(0)
                widget = item.widget() if item else None
                if widget is not None:
                    button_pfid = widget.property("mod_pfid")
                    if button_pfid:
                        buttons = self._mod_buttons.get(button_pfid)
                        if buttons and widget in buttons:
                            buttons.remove(widget)
                            if not buttons:
                                del self._mod_buttons[button_pfid]
                    widget.deleteLater()
            shown = state["shown"] or _MOD_BUTTON_PAGE_SIZE
            shown = min(shown, len(links))
            for _label, pfid, _url in links[:shown]:
                row_layout.addWidget(self._make_mod_toggle_button(pfid, bubble_width))
            state["shown"] = shown
            if shown < len(links):
                more_button = QPushButton(f"▼ {self.tr('More')} ({len(links) - shown})")
                more_button.setFlat(True)
                more_button.setMinimumWidth(bubble_width)
                more_button.setMaximumWidth(bubble_width)
                more_button.clicked.connect(
                    lambda: self._grow_mod_button_page(state, render_page)
                )
                row_layout.addWidget(more_button)

        render_page()
        return outer

    def _grow_mod_button_page(
        self, state: dict[str, int], render_page: Callable[[], None]
    ) -> None:
        state["shown"] = state["shown"] + _MOD_BUTTON_PAGE_SIZE
        render_page()

    def _refresh_mod_buttons_style(self) -> None:
        for pfid, buttons in self._mod_buttons.items():
            added = self._download_list.has_mod(pfid)
            for button in buttons:
                button.setText(
                    ("✓ " if added else "+ ")
                    + self._elided_mod_label(pfid, button=button)
                )

    def _on_mod_added(self, pfid: str) -> None:
        self._refresh_mod_buttons_style()
        self._queue_mod_tooltip_fetch(pfid)

    def _on_mod_removed(self, _pfid: str) -> None:
        self._refresh_mod_buttons_style()

    def _queue_mod_tooltip_fetch(self, pfid: str) -> None:
        if pfid in self._tooltip_fetch_pending or pfid in self._mod_tooltip_cache:
            return
        self._tooltip_fetch_pending.add(pfid)
        api_key = self.settings.steam_apikey.strip()
        cache_dir = Path(AppInfo().app_storage_folder) / "ai_mod_thumb_cache"
        worker = _ModDetailsWorker(pfid, api_key, cache_dir)
        worker.finished_ok.connect(self._on_mod_details_ready)
        worker.finished.connect(partial(self._detail_workers.remove, worker))
        self._detail_workers.append(worker)
        worker.start()

    def _on_mod_details_ready(self, pfid: str, tooltip_html: str) -> None:
        self._tooltip_fetch_pending.discard(pfid)
        self._mod_tooltip_cache[pfid] = tooltip_html
        if self._download_list.has_mod(pfid):
            self._download_list.set_item_tooltip(pfid, tooltip_html)

    def _format_message_html(self, msg: dict[str, str]) -> str:
        return _linkify(html.escape(msg["content"])).replace("\n", "<br>")

    def _is_at_bottom(self) -> bool:
        scrollbar = self.history_scroll.verticalScrollBar()
        return scrollbar.value() >= scrollbar.maximum() - 4

    def _scroll_to_bottom(self) -> None:
        scrollbar = self.history_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_history_layout(self) -> None:
        while self._history_layout.count() > 1:
            item = self._history_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()
        self._mod_buttons = {}

    def _remove_loading_bubble(self) -> None:
        for row in self._trace_rows:
            row.deleteLater()
        self._trace_rows = []
        if self._loading_bubble is not None:
            loading_row = self._loading_bubble.parentWidget()
            if loading_row is not None:
                loading_row.deleteLater()
            self._loading_bubble = None

    def _loading_text_html(self) -> str:
        return _linkify(html.escape(self._loading_text())).replace("\n", "<br>")

    def _refresh_loading_bubble(self) -> None:
        if self._loading_bubble is None:
            return
        was_at_bottom = self._is_at_bottom()
        self._set_bubble_html(self._loading_bubble, self._loading_text_html())
        if was_at_bottom:
            self._scroll_to_bottom()

    def _render_history(self, *, force_scroll: bool = False) -> None:
        was_at_bottom = force_scroll or self._is_at_bottom()
        self._remove_loading_bubble()
        self._clear_history_layout()
        for msg in self._store.as_list():
            mod_links = (
                _extract_mod_links(msg["content"])
                if msg["role"] == "assistant"
                else None
            )
            self._add_bubble(
                msg["role"],
                self._format_message_html(msg),
                msg.get("timestamp", ""),
                mod_links=mod_links,
            )
        if was_at_bottom:
            self._scroll_to_bottom()

    def _loading_text(self) -> str:
        if self._progress_message:
            if self._progress_total > 0:
                return self.tr("{current}/{total}: {message}").format(
                    current=self._progress_current,
                    total=self._progress_total,
                    message=self._progress_message,
                )
            return self._progress_message
        dots = "." * self._loading_dot_count
        return self.tr("Loading{dots}").format(dots=dots)

    def _start_loading(self) -> None:
        self._loading_dot_count = 1
        self._progress_current = 0
        self._progress_total = 0
        self._progress_message = ""
        self.progress_bar.setVisible(False)
        self._trace_rows = []
        was_at_bottom = self._is_at_bottom()
        self._loading_bubble = self._add_bubble("assistant", self._loading_text_html())
        if was_at_bottom:
            self._scroll_to_bottom()
        self._loading_timer.start(self._LOADING_INTERVAL_MS)

    def _stop_loading(self) -> None:
        self._loading_timer.stop()
        self.progress_bar.setVisible(False)
        self._progress_current = 0
        self._progress_total = 0
        self._progress_message = ""

    def _tick_loading(self) -> None:
        if self._progress_message:
            return
        self._loading_dot_count = (self._loading_dot_count % 3) + 1
        self._refresh_loading_bubble()

    def _on_progress(self, current: int, total: int, message: str) -> None:
        self._progress_current = current
        self._progress_total = total
        self._progress_message = message
        show_bar = message.startswith(self._LOCALIZATION_PROGRESS_PREFIXES)
        self.progress_bar.setVisible(show_bar)
        if show_bar:
            if total > 0:
                self.progress_bar.setRange(0, total)
                self.progress_bar.setValue(min(current, total))
                self.progress_bar.setFormat(
                    self.tr("{current}/{total}: {message}").format(
                        current=current,
                        total=total,
                        message=message,
                    )
                )
            else:
                self.progress_bar.setRange(0, 0)
                self.progress_bar.setFormat(message)
        self._refresh_loading_bubble()

    def _add_trace_row(self, brief: str, tooltip: str) -> QWidget:
        label = QLabel(f"<i>{html.escape(brief)}</i>")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setStyleSheet("color: gray; font-size: 11px;")
        label.setToolTip(tooltip)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(label)
        row_layout.addStretch()
        insert_index = self._history_layout.count() - 1
        if self._loading_bubble is not None:
            loading_row = self._loading_bubble.parentWidget()
            if loading_row is not None:
                found_index = self._history_layout.indexOf(loading_row)
                if found_index >= 0:
                    insert_index = found_index
        self._history_layout.insertWidget(insert_index, row)
        return row

    def _clear_chat(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._store.clear()
        self._render_history(force_scroll=True)

    def _current_model_id(self) -> str:
        return normalize_model_id(self.model_combo.currentData())

    def _current_localization_language(self) -> str:
        return str(self.localization_combo.currentData() or "")

    def _persist_ai_credentials(self) -> None:
        self.settings.ai_api_key = self.api_key_edit.text().strip()
        self.settings.ai_proxy = self.proxy_edit.text().strip()
        self.settings.ai_model = self._current_model_id()
        self.settings.ai_localization_language = self._current_localization_language()
        self.settings.save()

    def _select_model(self, model_id: str) -> None:
        index = self.model_combo.findData(model_id)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        self.settings.ai_model = normalize_model_id(model_id)
        self.settings.save()

    def _steam_apikey_context_line(self) -> str:
        key = self.settings.steam_apikey.strip()
        if key:
            return f"Steam Web API key: configured ({len(key)} chars)."
        return "Steam Web API key: not configured."

    def _localization_context_line(self) -> str:
        lang_code = self._current_localization_language()
        if not lang_code:
            return ""
        lang_label = dict(LOCALIZATION_LANGUAGES).get(lang_code, lang_code)
        return (
            f"User's preferred mod localization language is {lang_code} "
            f"({lang_label}). Proactively offer to search for {lang_code} "
            "localizations of active mods lacking them via "
            f"find_localizations_for_active_mods with language='{lang_code}'. "
        )

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
        steam_line = self._steam_apikey_context_line()
        localization_line = self._localization_context_line()
        return (
            f"You are a helpful assistant for RimSort {version}. "
            f"RimWorld version: {game_version}. Active mods: {len(active_mods)}. "
            f"{steam_line} {localization_line}"
            "Answer questions about mod lists. Read-only changes are not applied directly; "
            "use queue_sort_mods, queue_save_mods, queue_download, or queue_run_game only "
            "when the user explicitly asks and RimSort GUI is running. "
            "The user can add mods you mention to their download list themselves via "
            "UI buttons; do not call queue_download unless the user explicitly asks you "
            "to start downloading. "
            "Do not use Markdown formatting (no **, ##, ```, or bullet lists), "
            "except for mod links as described below. "
            "When you mention a specific Steam Workshop mod, present it as a link "
            "in this exact form: [Mod Name (publishedfileid)]"
            "(https://steamcommunity.com/sharedfiles/filedetails/?id=<publishedfileid>) "
            "so it renders as a clickable hyperlink whose visible text is the mod "
            "name and ID. "
            "CRITICAL: NEVER invent Steam Workshop publishedfileid values. "
            "Only cite IDs returned by search_workshop_mods, "
            "find_localizations_for_active_mods, or validate_workshop_ids. "
            "If the user is looking for mods, ask whether they want them added to the "
            "download list. "
            "For localization requests, ALWAYS call find_localizations_for_active_mods "
            "with the appropriate language first. "
            "Before showing a final localization list, verify IDs with "
            "validate_workshop_ids and report only valid IDs. "
            "Before queue_download, use only IDs from tool results; "
            "queue_download validates IDs automatically. "
            "NEVER claim steam_apikey is missing unless get_instance_summary or "
            "a workshop search tool returned that error. "
            "Tools: describe_mod, search_installed_mods, search_workshop_mods, "
            "search_steam_workshop (same as search_workshop_mods), "
            "find_localizations_for_active_mods, validate_workshop_ids, "
            "list_missing_deps, get_instance_summary, "
            "read_log (source player or rimsort), list_active_mods, list_installed_mods.\n\n"
            f"{mods_preview}"
        )

    def _on_tool_trace(
        self, name: str, args: dict[str, Any], result: dict[str, Any]
    ) -> None:
        brief = _format_tool_trace(name, args, result)
        tooltip = _format_tool_tooltip(name, args, result)
        was_at_bottom = self._is_at_bottom()
        self._trace_rows.append(self._add_trace_row(brief, tooltip))
        if was_at_bottom:
            self._scroll_to_bottom()

    def _send(self) -> None:
        text = self.input_edit.text().strip()
        if not text or (self._worker and self._worker.isRunning()):
            return
        self._persist_ai_credentials()
        self.input_edit.clear()
        self._store.append("user", text)
        self._sent_history.append(text)
        self._history_cursor = None
        self._history_draft = ""
        self._render_history(force_scroll=True)
        self._start_loading()

        messages = [{"role": "system", "content": self._system_context()}]
        messages.extend(self._store.as_list())
        provider = GeminiProvider(
            self.settings.ai_api_key,
            proxy=self.settings.ai_proxy,
            model=self._current_model_id(),
        )
        self.send_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self._worker = _CompletionWorker(
            provider,
            messages,
            steam_apikey_override=self.settings.steam_apikey.strip() or None,
        )
        self._worker.tool_trace.connect(self._on_tool_trace)
        self._worker.progress.connect(self._on_progress)
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
        was_at_bottom = self._is_at_bottom()
        self._remove_loading_bubble()
        timestamp = datetime.now().strftime("%H:%M:%S")  # noqa: DTZ005
        error_html = f"<b>{self.tr('Error')}:</b> {_linkify(html.escape(message))}"
        self._add_bubble("assistant", error_html, timestamp)
        if was_at_bottom:
            self._scroll_to_bottom()

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

    # -- Download list: compatibility check + download -----------------

    def _on_download_list_requested(self, pfids: list[str]) -> None:
        if not pfids:
            return
        self._persist_ai_credentials()
        if not self.settings.ai_api_key.strip():
            self._start_download(pfids)
            return

        provider = GeminiProvider(
            self.settings.ai_api_key,
            proxy=self.settings.ai_proxy,
            model=self._current_model_id(),
        )
        prompt = self._compatibility_check_prompt(pfids)
        self._compat_worker = _CompatibilityCheckWorker(
            provider, [{"role": "user", "content": prompt}]
        )
        self._compat_worker.finished_ok.connect(partial(self._on_compat_result, pfids))
        self._compat_worker.finished_error.connect(
            lambda _msg: self._start_download(pfids)
        )
        self._compat_worker.start()

    def _compatibility_check_prompt(self, pfids: list[str]) -> str:
        mod_lines = "\n".join(
            f"{pfid}: {self._mod_titles.get(pfid, pfid)}" for pfid in pfids
        )
        active_mods = mod_context.list_active_mods(
            self.metadata_controller, self._get_active_paths()
        )
        active_lines = "\n".join(
            f"{m.get('package_id', '')}: {m.get('name', '')}" for m in active_mods[:200]
        )
        game_version = self.metadata_controller.game_version
        return (
            "You check RimWorld mod compatibility. "
            f"Game version: {game_version}.\n"
            f"Mods to download:\n{mod_lines}\n\n"
            f"Currently active mods:\n{active_lines}\n\n"
            "Reply with ONLY a raw JSON object (no markdown fences, no prose): "
            '{"incompatible": [{"publishedfileid": "...", "reason": "..."}]}. '
            'If everything looks compatible, reply {"incompatible": []}.'
        )

    def _on_compat_result(self, pfids: list[str], text: str) -> None:
        incompatible = self._parse_compat_response(text)
        if not incompatible:
            self._start_download(pfids)
            return
        self._show_compat_warning(pfids, incompatible)

    def _parse_compat_response(self, text: str) -> list[dict[str, str]]:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
        items = data.get("incompatible", [])
        if not isinstance(items, list):
            return []
        return [
            item
            for item in items
            if isinstance(item, dict) and item.get("publishedfileid")
        ]

    def _show_compat_warning(
        self, pfids: list[str], incompatible: list[dict[str, str]]
    ) -> None:
        incompatible_ids = {str(item["publishedfileid"]) for item in incompatible}
        lines = [self.tr("Potentially incompatible mods found:")]
        for item in incompatible:
            pfid = str(item["publishedfileid"])
            name = self._mod_titles.get(pfid, pfid)
            reason = str(item.get("reason", ""))
            lines.append(f"- {name}: {reason}")
        timestamp = datetime.now().strftime("%H:%M:%S")  # noqa: DTZ005
        was_at_bottom = self._is_at_bottom()
        text_html = _linkify(html.escape("\n".join(lines))).replace("\n", "<br>")
        self._add_bubble("assistant", text_html, timestamp)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 2, 0, 6)
        download_all_btn = QPushButton(self.tr("Download anyway"))
        skip_incompatible_btn = QPushButton(self.tr("Skip incompatible mods"))
        compatible_ids = [pfid for pfid in pfids if pfid not in incompatible_ids]

        def resolve(chosen_ids: list[str]) -> None:
            download_all_btn.setEnabled(False)
            skip_incompatible_btn.setEnabled(False)
            self._start_download(chosen_ids)

        download_all_btn.clicked.connect(lambda: resolve(pfids))
        skip_incompatible_btn.clicked.connect(lambda: resolve(compatible_ids))
        button_layout.addWidget(download_all_btn)
        button_layout.addWidget(skip_incompatible_btn)
        button_layout.addStretch()
        self._history_layout.insertWidget(self._history_layout.count() - 1, button_row)
        if was_at_bottom:
            self._scroll_to_bottom()

    def _start_download(self, pfids: list[str]) -> None:
        if pfids:
            EventBus().do_steamcmd_download.emit(pfids)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._persist_ai_credentials()
        super().closeEvent(event)

    def show_non_modal(self) -> None:
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.show()
