import gc
import os
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Deque, List, Optional, Tuple

import requests
from loguru import logger
from PySide6.QtCore import QObject, QPoint, QRegularExpression, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.controllers.settings_controller import SettingsController
from app.utils.app_info import AppInfo
from app.utils.generic import launch_process
from app.views.dialogue import show_information, show_warning


class LogPatternManager:
    """Centralized management of regex patterns for log parsing and highlighting."""

    # Pre-compiled patterns for syntax highlighting
    TIMESTAMP_PATTERN = re.compile(r"\d{1,2}:\d{2}:\d{2} [AP]M")
    INFO_PATTERN = re.compile(
        r"\b(info|initialized|loaded|start(ed)?|starting|done|success)\b", re.IGNORECASE
    )
    KEYBIND_PATTERN = re.compile(r"key binding conflict", re.IGNORECASE)
    MOD_ISSUE_PATTERN = re.compile(r"\[([^\]]+)\]")
    WARNING_PATTERN = re.compile(
        r"\b(warning|warn|deprecat|deprecated)\b", re.IGNORECASE
    )
    WARNING_SHORT_PATTERN = re.compile(r"\[W\]")
    ERROR_PATTERN = re.compile(
        r"\b(error|failed|exception|fatal|critical)\b|\[E\]", re.IGNORECASE
    )
    ERROR_SHORT_PATTERN = re.compile(r"\[E\]")
    EXCEPTION_PATTERN = re.compile(r".*Exception.*:|.*Error.*:")
    STACK_TRACE_PATTERN = re.compile(r"^\s*at .*")

    # Pre-compiled patterns for log analysis and filtering
    INFO_FILTER_PATTERN = re.compile(
        r"\b(info|initialized|loaded|start(ed)?|starting|done|success|loaded|complete)\b",
        re.IGNORECASE,
    )
    KEYBIND_FILTER_PATTERN = re.compile(r"key binding conflict", re.IGNORECASE)
    MOD_ISSUE_FILTER_PATTERN = re.compile(
        r"(\[.*\].*(error|warning|exception))|(mod.*(conflict|issue))", re.IGNORECASE
    )
    WARNING_FILTER_PATTERN = re.compile(
        r"\b(warning|warn|deprecat|deprecated)\b|\[W\]", re.IGNORECASE
    )
    ERROR_FILTER_PATTERN = re.compile(
        r"\b(error|failed|fatal|critical)\b|\[E\]", re.IGNORECASE
    )
    EXCEPTION_FILTER_PATTERN = re.compile(r"exception", re.IGNORECASE)

    PATHLIKE_PATTERN = re.compile(
        r"""
        (?:
            [a-zA-Z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]+    # Windows paths
            |
            /(?:[^/\s]+/)*[^/\s]+                                      # Unix/macOS paths
        )
        """,
        re.VERBOSE,
    )

    @classmethod
    def get_highlight_patterns(cls) -> List[Tuple[re.Pattern[str], str]]:
        """Get all patterns for syntax highlighting with their priority order."""
        return [
            (cls.TIMESTAMP_PATTERN, "timestamp"),
            (cls.INFO_PATTERN, "info"),
            (cls.KEYBIND_PATTERN, "keybind"),
            (cls.MOD_ISSUE_PATTERN, "mod_issue"),
            (cls.WARNING_PATTERN, "warning"),
            (cls.WARNING_SHORT_PATTERN, "warning"),
            (cls.ERROR_PATTERN, "error"),
            (cls.ERROR_SHORT_PATTERN, "error"),
            (cls.EXCEPTION_PATTERN, "exception"),
            (cls.STACK_TRACE_PATTERN, "exception"),
        ]

    @classmethod
    def get_filter_pattern(cls, filter_name: str) -> Optional[re.Pattern[str]]:
        """Get pattern for specific filter type."""
        patterns = {
            "info": cls.INFO_FILTER_PATTERN,
            "keybind": cls.KEYBIND_FILTER_PATTERN,
            "mod_issue": cls.MOD_ISSUE_FILTER_PATTERN,
            "warning": cls.WARNING_FILTER_PATTERN,
            "error": cls.ERROR_FILTER_PATTERN,
            "exception": cls.EXCEPTION_FILTER_PATTERN,
        }
        return patterns.get(filter_name.lower())


class LogContentStorage:
    """Memory-efficient storage for log content using chunked storage."""

    def __init__(self, max_chunk_size: int = 1024 * 1024):  # 1MB chunks by default
        self.chunks: Deque[str] = deque()
        self.max_chunk_size = max_chunk_size
        self.total_size = 0
        self.line_count = 0

    def append(self, content: str) -> None:
        """Append content in memory-efficient chunks with optimized string handling."""
        if not content:
            return

        # Use a list to collect lines for more efficient string building
        lines = content.splitlines(keepends=True)
        current_chunk_lines: List[str] = []
        current_chunk_size = 0

        for line in lines:
            line_length = len(line)

            # If adding this line would exceed chunk size and we have existing content
            if (
                current_chunk_size + line_length > self.max_chunk_size
                and current_chunk_lines
            ):
                # Join the current chunk and add to deque
                self.chunks.append("".join(current_chunk_lines))
                current_chunk_lines = [line]
                current_chunk_size = line_length
            else:
                current_chunk_lines.append(line)
                current_chunk_size += line_length

            self.line_count += 1

        # Add any remaining content as a chunk
        if current_chunk_lines:
            self.chunks.append("".join(current_chunk_lines))

        self.total_size += len(content)

        # Check if total size exceeds a certain limit (e.g., 10MB)
        if self.total_size > 10 * 1024 * 1024:  # 10MB limit
            self.remove_oldest_chunk()

    def remove_oldest_chunk(self) -> None:
        """Remove the oldest chunk to maintain memory limits."""
        if self.chunks:
            removed_chunk = self.chunks.popleft()  # Remove the oldest chunk
            self.total_size -= len(removed_chunk)  # Update total size
            logger.debug(f"Removed oldest chunk of size {len(removed_chunk)} bytes.")

    def clear(self) -> None:
        """Clear all stored content and trigger garbage collection."""
        self.chunks.clear()
        self.total_size = 0
        self.line_count = 0
        # Force garbage collection to reclaim memory immediately
        gc.collect(generation=2)  # Collect all generations for maximum memory recovery

    def get_full_content(self) -> str:
        """Get the full content as a string (use sparingly)."""
        return "".join(self.chunks)

    def get_lines(
        self, start_line: int = 0, end_line: Optional[int] = None
    ) -> List[str]:
        """Get specific lines efficiently without loading entire content."""
        lines = []
        current_line = 0

        for chunk in self.chunks:
            chunk_lines = chunk.splitlines(keepends=True)
            for line in chunk_lines:
                if current_line >= start_line:
                    lines.append(line)
                    if end_line and current_line >= end_line:
                        return lines
                current_line += 1

        return lines

    def __len__(self) -> int:
        return self.total_size

    def __str__(self) -> str:
        return self.get_full_content()


class LogHighlighter(QSyntaxHighlighter):
    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)

        # Define color formats
        self.timestamp_format = self._make_format("#15FF00")
        self.info_format = self._make_format("#00FF0D", bold=True)
        self.keybind_format = self._make_format("#EEFF00", bold=True)
        self.mod_issue_format = self._make_format("#FF8C00", bold=True)
        self.warning_format = self._make_format("#FF8C00", bold=True)
        self.error_format = self._make_format("#FF0000", bold=True)
        self.exception_format = self._make_format("#FF0000", bold=True)

        self.search_format = QTextCharFormat()
        self.search_format.setBackground(QColor("#005500"))

        self.search_term: Optional[str] = None
        self._search_regex: Optional[re.Pattern[str]] = None  # Cache compiled regex

        # Define patterns with priority (higher index = higher priority)
        # Use patterns from LogPatternManager for consistency
        self.patterns = [
            (LogPatternManager.TIMESTAMP_PATTERN, self.timestamp_format),
            (LogPatternManager.INFO_PATTERN, self.info_format),
            (LogPatternManager.KEYBIND_PATTERN, self.keybind_format),
            (LogPatternManager.MOD_ISSUE_PATTERN, self.mod_issue_format),
            (LogPatternManager.WARNING_PATTERN, self.warning_format),
            (LogPatternManager.WARNING_SHORT_PATTERN, self.warning_format),
            (LogPatternManager.ERROR_PATTERN, self.error_format),
            (LogPatternManager.ERROR_SHORT_PATTERN, self.error_format),
            (LogPatternManager.EXCEPTION_PATTERN, self.exception_format),
            (LogPatternManager.STACK_TRACE_PATTERN, self.exception_format),
        ]

    def set_highlight_color(self, color: QColor) -> None:
        """Set the color used for search term highlighting and quick navigation."""
        self.search_format.setBackground(color)
        self.rehighlight()

    def set_search_term(self, term: Optional[str]) -> None:
        """Set the current search term and compile regex for highlighting."""
        self.search_term = term
        if term:
            try:
                self._search_regex = re.compile(re.escape(term), re.IGNORECASE)
            except re.error:
                self._search_regex = None
        else:
            self._search_regex = None
        self.rehighlight()

    def _make_format(self, color: str, bold: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt

    def highlightBlock(self, text: str) -> None:
        # Highlight search matches first (highest priority)
        if self._search_regex:
            try:
                for match in self._search_regex.finditer(text):
                    start, end = match.span()
                    self.setFormat(start, end - start, self.search_format)
            except Exception:
                pass
        # Apply other patterns
        for pattern, fmt in self.patterns:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)


class PlayerLogTab(QWidget):
    matches: List[QTextCursor]
    last_log_size: int
    total_lines_label: QPushButton
    info_label: QPushButton
    keybind_label: QPushButton
    mod_issues_label: QPushButton
    warnings_label: QPushButton
    errors_label: QPushButton
    exceptions_label: QPushButton
    all_issues_label: QPushButton
    match_count_label: QLabel
    _file_change_debounce_timer: QTimer
    # Precompile regex patterns for filtering and analysis once at class level
    _info_pattern = re.compile(
        r"\b(info|initialized|loaded|start(ed)?|done|success)\b", re.IGNORECASE
    )
    _keybind_pattern = re.compile(r"key binding conflict", re.IGNORECASE)
    _mod_issue_pattern = re.compile(
        r"(\[.*\].*(error|warning|exception))|(mod.*(conflict|issue))", re.IGNORECASE
    )
    _warning_pattern = re.compile(
        r"\b(warning|warn|deprecat|deprecated)\b|\[W\]", re.IGNORECASE
    )
    _error_pattern = re.compile(r"\b(error|failed|fatal)\b|\[E\]", re.IGNORECASE)
    _exception_pattern = re.compile(r"exception", re.IGNORECASE)

    def __init__(self, settings_controller: SettingsController) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.player_log_path: Optional[Path] = None
        self.log_storage = LogContentStorage()  # Use new memory-efficient storage
        self.current_log_content: str = ""
        self.filtered_content: str = ""
        self.log_stats: dict[str, int] = {
            "total_lines": 0,
            "infos": 0,
            "keybinds": 0,
            "mod_issues": 0,
            "warnings": 0,
            "errors": 0,
            "exceptions": 0,
        }
        self.highlighter: LogHighlighter
        self.log_display: QTextEdit
        self.current_match_index: int = -1
        self.matches = []
        self.filter_combo: Optional[QComboBox] = None
        self.mod_filter_input: Optional[QLineEdit] = None
        self.last_log_size: int = 0
        self._last_nav_pattern: Optional[str] = None
        self._pattern_matches_cache: dict[str, List[QTextCursor]] = {}
        self._pattern_regex_cache: dict[str, QRegularExpression] = {}

        self.bookmarked_lines: set[int] = set()  # Store line numbers of bookmarks

        self.quick_nav_highlight_format = QTextCharFormat()
        self.quick_nav_highlight_format.setBackground(QColor("#0076FC"))

        self._file_change_debounce_timer = QTimer(self)
        self._file_change_debounce_timer.setSingleShot(True)
        self._file_change_debounce_timer.setInterval(
            1000
        )  # 1000ms debounce interval less than 1000ms breaks log updates
        self._file_change_debounce_timer.timeout.connect(self._process_file_change)

        self.init_ui()
        # Delay loading the log by 5 seconds after initialization
        QTimer.singleShot(5000, self._delayed_load_log)

    def _collapse_repeated_lines(self, lines: List[str]) -> List[str]:
        """Collapse consecutive repeated lines into a single line with a count."""
        if not lines:
            return []
        collapsed_lines = []
        prev_line = lines[0]
        count = 1
        for line in lines[1:]:
            if line == prev_line:
                count += 1
            else:
                if count > 1:
                    collapsed_lines.append(f"{prev_line} (Repeated {count} times)")
                else:
                    collapsed_lines.append(prev_line)
                prev_line = line
                count = 1
        # Handle last group
        if count > 1:
            collapsed_lines.append(f"{prev_line} (Repeated {count} times)")
        else:
            collapsed_lines.append(prev_line)
        return collapsed_lines

    def _delayed_load_log(self) -> None:
        if self.settings_controller.settings.auto_load_player_log_on_startup:
            self.player_log_path = self._get_player_log_path()
            if self.player_log_path is not None:
                self.load_log()

    def _on_auto_load_player_log_on_startup_toggled(self, checked: bool) -> None:
        self.settings_controller.settings.auto_load_player_log_on_startup = checked
        self.settings_controller.settings.save()

    def set_highlight_color(self, color: QColor) -> None:
        self.highlighter.set_highlight_color(color)
        self.quick_nav_highlight_format.setBackground(color)
        self._highlight_quick_navigation(color)

    def _highlight_quick_navigation(self, color: QColor) -> None:
        """Highlight quick navigation matches with the given color."""
        self.highlighter.set_highlight_color(color)
        self.search_text_changed(self.search_input.text() if self.search_input else "")

    def _clear_log_display(self) -> None:
        self.log_display.clear()

    def clear_log(self) -> None:
        """Clear the log content, statistics, and display."""
        self.log_storage.clear()
        self.log_stats = {
            "total_lines": 0,
            "infos": 0,
            "keybinds": 0,
            "mod_issues": 0,
            "warnings": 0,
            "errors": 0,
            "exceptions": 0,
        }
        self.last_log_size = 0
        self._clear_log_display()
        self._update_statistics()
        self._update_file_info()

    def scroll_to_end(self) -> None:
        cursor = self.log_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_display.setTextCursor(cursor)
        self.log_display.ensureCursorVisible()

    def _get_player_log_path(self) -> Optional[Path]:
        try:
            current_instance: str = self.settings_controller.settings.current_instance
            config_folder: str = self.settings_controller.settings.instances[
                current_instance
            ].config_folder
            player_log_path: Path = Path(config_folder).parent / "Player.log"
            if player_log_path.exists():
                return player_log_path
        except Exception:
            pass
        return None

    def pick_highlight_color(self) -> None:
        color = QColorDialog.getColor(
            self.highlighter.search_format.background().color(),
            self,
            self.tr("Pick Highlight Color"),
        )
        if color.isValid():
            self.set_highlight_color(color)

    def init_ui(self) -> None:
        """Initialize the main UI layout and components."""
        self.main_layout = QVBoxLayout()
        self._init_left_panel()
        self._init_middle_panel()

        # Add context menu action for bookmarking lines
        self.log_display.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.log_display.customContextMenuRequested.connect(self.show_context_menu)

        self.horizontal_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.horizontal_splitter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.horizontal_splitter.addWidget(self.left_panel)
        self.horizontal_splitter.addWidget(self.middle_panel)
        self.horizontal_splitter.setSizes([400, 1250])
        self.horizontal_splitter.setStretchFactor(0, 0)
        self.horizontal_splitter.setStretchFactor(1, 1)

        self.main_layout.addWidget(self.horizontal_splitter)
        self.setLayout(self.main_layout)

    def _init_left_panel(self) -> None:
        """Initialize the left panel UI components with improved layout."""
        self.left_panel = QWidget()
        self.left_panel.setMinimumWidth(350)
        self.left_panel.setMaximumWidth(500)
        self.left_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setSpacing(1)
        self.left_layout.setContentsMargins(1, 1, 1, 1)

        self._init_file_info_group()
        self._init_statistics_group()
        self._init_controls_group()

        self._init_search_filter_group()
        self._init_quick_navigation_group()

    def _init_middle_panel(self) -> None:
        """Initialize the middle panel UI components."""
        self.middle_panel = QWidget()
        self.middle_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.middle_layout = QVBoxLayout(self.middle_panel)
        self.middle_layout.setContentsMargins(8, 8, 8, 8)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 10))
        self.log_display.setMinimumSize(400, 200)
        self.log_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.log_display.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.log_display.customContextMenuRequested.connect(self.show_context_menu)
        self.middle_layout.addWidget(self.log_display)

        self.highlighter = LogHighlighter(self.log_display.document())

    def _init_file_info_group(self) -> None:
        file_info_group = QGroupBox(self.tr("File Info"))
        file_info_layout = QVBoxLayout()
        file_info_group.setLayout(file_info_layout)

        file_info_layout.setSpacing(1)
        file_info_layout.setContentsMargins(1, 1, 1, 1)

        file_info_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )

        self.file_path_label = QLabel(self.tr("Path:"))
        self.file_path_label.setWordWrap(True)
        file_info_layout.addWidget(self.file_path_label)

        self.file_size_label = QLabel(self.tr("Size:"))
        file_info_layout.addWidget(self.file_size_label)

        self.last_modified_label = QLabel(self.tr("Modified:"))
        file_info_layout.addWidget(self.last_modified_label)

        self.growth_label = QLabel("")
        self.growth_label.setStyleSheet("color: green; font-weight: bold;")
        file_info_layout.addWidget(self.growth_label)

        self.left_layout.addWidget(file_info_group)

        for i in range(file_info_layout.count()):
            item = file_info_layout.itemAt(i)
            if item:
                widget = item.widget()
                if widget:
                    widget.setContentsMargins(0, 0, 0, 0)
                    widget.setSizePolicy(
                        QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
                    )

    def _init_statistics_group(self) -> None:
        stats_group = QGroupBox(self.tr("Statistics"))
        stats_layout = QVBoxLayout()
        stats_group.setLayout(stats_layout)
        stats_layout.setSpacing(1)
        stats_layout.setContentsMargins(1, 1, 1, 1)

        def create_stat_button(text: str, color: str, filter_name: str) -> QPushButton:
            btn = QPushButton(text)
            btn.setStyleSheet(
                f"color: {color}; background: transparent; border: none; text-align: left;"
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFlat(True)
            btn.clicked.connect(lambda: self._on_stat_button_clicked(filter_name))
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            return btn

        self.total_lines_label = create_stat_button(
            self.tr("Total Lines: 0"), "#00FF00", self.tr("All Entries")
        )
        self.info_label = create_stat_button(
            self.tr("Infos: 0"), "#00FF00", self.tr("Infos Only")
        )
        self.keybind_label = create_stat_button(
            self.tr("Keybinds: 0"), "#EEFF00", self.tr("Keybinds Only")
        )
        self.mod_issues_label = create_stat_button(
            self.tr("Mod Issues: 0"), "#FF8C00", self.tr("Mod Issues")
        )
        self.warnings_label = create_stat_button(
            self.tr("Warnings: 0"), "#FF8C00", self.tr("Warnings Only")
        )
        self.errors_label = create_stat_button(
            self.tr("Errors: 0"), "#FF0000", self.tr("Errors Only")
        )
        self.exceptions_label = create_stat_button(
            self.tr("Exceptions: 0"), "#FF0000", self.tr("Exceptions Only")
        )
        self.all_issues_label = create_stat_button(
            self.tr("All Issues: 0"), "#FF0000", self.tr("All Issues")
        )

        stats_layout.addWidget(self.total_lines_label)
        stats_layout.addWidget(self.info_label)
        stats_layout.addWidget(self.keybind_label)
        stats_layout.addWidget(self.mod_issues_label)
        stats_layout.addWidget(self.warnings_label)
        stats_layout.addWidget(self.errors_label)
        stats_layout.addWidget(self.exceptions_label)
        stats_layout.addWidget(self.all_issues_label)

        self.left_layout.addWidget(stats_group)

    def _on_stat_button_clicked(self, filter_name: str) -> None:
        if self.filter_combo:
            index = self.filter_combo.findText(filter_name)
            if index != -1:
                self.filter_combo.setCurrentIndex(index)
                self.apply_filter()

    def _init_controls_group(self) -> None:
        controls_group = QGroupBox(self.tr("Controls"))
        controls_layout = QVBoxLayout()
        controls_group.setLayout(controls_layout)
        controls_layout.setSpacing(1)
        controls_layout.setContentsMargins(1, 1, 1, 1)

        self.auto_load_player_log_on_startup_checkbox = QCheckBox(
            self.tr("Auto Load Game Log on Startup")
        )
        self.auto_load_player_log_on_startup_checkbox.setToolTip(
            self.tr("If checked, the Game log will be loaded automatically on startup.")
        )
        controls_layout.addWidget(self.auto_load_player_log_on_startup_checkbox)
        self.auto_load_player_log_on_startup_checkbox.setChecked(
            self.settings_controller.settings.auto_load_player_log_on_startup
        )
        self.auto_load_player_log_on_startup_checkbox.toggled.connect(
            self._on_auto_load_player_log_on_startup_toggled
        )

        self.real_time_monitor_checkbox = QCheckBox(
            self.tr("Enable Real-Time Log Monitoring")
        )
        self.real_time_monitor_checkbox.setToolTip(
            self.tr("Enable real-time monitoring of Player.log file changes.")
        )
        self.real_time_monitor_checkbox.toggled.connect(
            self.toggle_real_time_monitoring
        )
        controls_layout.addWidget(self.real_time_monitor_checkbox)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(1)
        self.refresh_button = QPushButton(self.tr("Refresh"))
        self.refresh_button.clicked.connect(self.refresh_log)
        self.export_button = QPushButton(self.tr("Export"))
        self.export_button.clicked.connect(self.export_log)
        self.clear_button = QPushButton(self.tr("Clear Log Display"))
        self.clear_button.clicked.connect(self.clear_log)
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.export_button)
        button_layout.addWidget(self.clear_button)
        controls_layout.addWidget(self.real_time_monitor_checkbox)

        load_buttons_layout = QHBoxLayout()
        load_buttons_layout.setSpacing(1)
        self.load_default_button = QPushButton(self.tr("Load Game Log"))
        self.load_default_button.setToolTip(
            self.tr("Loads the game's Player.log file.")
        )
        self.load_default_button.clicked.connect(self.load_default_log)
        load_buttons_layout.addWidget(self.load_default_button)

        self.load_file_button = QPushButton(self.tr("Load Log from File"))
        self.load_file_button.setToolTip(
            self.tr("Open a file dialog to select a log file")
        )
        self.load_file_button.clicked.connect(self.load_log_from_file)
        load_buttons_layout.addWidget(self.load_file_button)

        self.load_link_button = QPushButton(self.tr("Load Log from Link"))
        self.load_link_button.setToolTip(self.tr("Load log content from a URL"))
        self.load_link_button.clicked.connect(self.load_log_from_link)
        load_buttons_layout.addWidget(self.load_link_button)

        controls_layout.addLayout(load_buttons_layout)
        controls_group.setLayout(controls_layout)

        self.left_layout.addWidget(controls_group)

    def _init_search_filter_group(self) -> None:
        """Initialize the Search and Filter group UI components."""
        search_filter_group = QGroupBox(self.tr("Search and Filter"))
        search_filter_layout = QVBoxLayout()
        search_filter_group.setLayout(search_filter_layout)
        search_filter_layout.setSpacing(1)
        search_filter_layout.setContentsMargins(1, 1, 1, 1)

        # Search input and match count label
        search_input_layout = QHBoxLayout()
        search_input_layout.setSpacing(1)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Search log entries..."))
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(300)  # 300ms debounce
        self.search_input.textChanged.connect(self._on_search_text_changed_debounced)
        self._search_debounce_timer.timeout.connect(self._do_search_text_changed)
        search_input_layout.addWidget(self.search_input)

        self.match_count_label = QLabel("0/0")
        self.match_count_label.setObjectName("match_count_label")
        search_input_layout.addWidget(self.match_count_label)
        search_filter_layout.addLayout(search_input_layout)

        # Filter combo box and mod filter input
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(1)
        self.filter_combo = QComboBox()
        self.filter_combo.setMinimumWidth(140)
        self.filter_combo.addItems(
            [
                self.tr("All Entries"),
                self.tr("Infos Only"),
                self.tr("Keybinds Only"),
                self.tr("Mod Issues"),
                self.tr("Warnings Only"),
                self.tr("Errors Only"),
                self.tr("Exceptions Only"),
                self.tr("All Issues"),
            ]
        )
        self.filter_combo.currentIndexChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_combo)

        self.mod_filter_input = QLineEdit()
        self.mod_filter_input.setPlaceholderText(self.tr("Filter by mod name..."))
        self.mod_filter_input.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.mod_filter_input)
        search_filter_layout.addLayout(filter_layout)

        # Highlight color and navigation buttons layout
        highlight_nav_layout = QHBoxLayout()
        highlight_nav_layout.setSpacing(1)

        self.color_picker_button = QPushButton(self.tr("Highlight Color"))
        self.color_picker_button.setToolTip(
            self.tr("Pick color for search and navigation highlighting")
        )
        self.color_picker_button.setMaximumHeight(24)
        self.color_picker_button.clicked.connect(self.pick_highlight_color)

        self.prev_button = QPushButton(self.tr("Previous"))
        self.prev_button.setMaximumHeight(24)
        self.prev_button.clicked.connect(self.goto_previous_match)

        self.next_button = QPushButton(self.tr("Next"))
        self.next_button.setMaximumHeight(24)
        self.next_button.clicked.connect(self.goto_next_match)

        highlight_nav_layout.addWidget(self.color_picker_button)
        highlight_nav_layout.addWidget(self.prev_button)
        highlight_nav_layout.addWidget(self.next_button)

        search_filter_layout.addLayout(highlight_nav_layout)

        self.left_layout.addWidget(search_filter_group)

    def _make_prev_callback(self, pattern: str) -> Callable[[], None]:
        return lambda: self.goto_previous_pattern(pattern)

    def _make_next_callback(self, pattern: str) -> Callable[[], None]:
        return lambda: self.goto_next_pattern(pattern)

    def _init_quick_navigation_group(self) -> None:
        def create_nav_button(
            text: str, tooltip: str, callback: Callable[[], None]
        ) -> QPushButton:
            btn = QPushButton(text)
            btn.setToolTip(tooltip)
            btn.clicked.connect(callback)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setMaximumHeight(20)
            btn.setMinimumWidth(30)
            btn.setMaximumWidth(30)
            return btn

        nav_group = QGroupBox(self.tr("Quick Navigation"))
        nav_layout = QGridLayout()
        nav_group.setLayout(nav_layout)
        nav_layout.setSpacing(4)
        nav_layout.setContentsMargins(4, 4, 4, 4)

        # Define labels for log types
        log_types = [
            (self.tr("Info"), r"(?i)(info|initialized|loaded|start(ed)?|done|success)"),
            (self.tr("Keybind"), r"key binding conflict"),
            (self.tr("Mod_issue"), r"\[.*\]"),
            (self.tr("Warning"), r"(?i)(warning|warn|deprecat|\[W\])"),
            (self.tr("Error"), r"(?i)(error|failed|fatal|critical|Error:|\[E\])"),
            (self.tr("Exception"), r"Exception"),
        ]

        for row, (label_text, pattern) in enumerate(log_types):
            prev_btn = create_nav_button(
                "<",
                self.tr("Jump to previous {lower} entry").format(
                    lower=label_text.lower()
                ),
                self._make_prev_callback(pattern),
            )
            next_btn = create_nav_button(
                ">",
                self.tr("Jump to next {lower} entry").format(lower=label_text.lower()),
                self._make_next_callback(pattern),
            )
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumWidth(80)
            label.setMaximumWidth(100)

            nav_layout.addWidget(prev_btn, row, 0)
            nav_layout.addWidget(label, row, 1)
            nav_layout.addWidget(next_btn, row, 2)

        # Scroll to end button spans all columns
        scroll_to_end_btn = QPushButton(self.tr("Scroll to End"))
        scroll_to_end_btn.setToolTip(self.tr("Scroll to the end of the log display"))
        scroll_to_end_btn.clicked.connect(self.scroll_to_end)
        scroll_to_end_btn.setMaximumHeight(24)
        scroll_to_end_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        nav_layout.addWidget(scroll_to_end_btn, len(log_types), 0, 1, 3)

        self.left_layout.addWidget(nav_group)

    def on_file_changed(self) -> None:
        """Handle file changed signal by starting debounce timer."""
        logger.debug("File changed signal received, starting debounce timer.")
        # Restart the debounce timer on every file change to ensure continuous updates
        if self._file_change_debounce_timer.isActive():
            self._file_change_debounce_timer.stop()
        self._file_change_debounce_timer.start()

    def _process_file_change(self) -> None:
        """Process the file change after debounce interval."""
        logger.debug("Debounce timer triggered, processing file change.")
        try:
            if self.player_log_path is None:
                logger.debug("Player log path is None in _process_file_change.")
                return
            current_size = self.player_log_path.stat().st_size
            logger.debug(
                f"_process_file_change: current_size={current_size}, last_log_size={self.last_log_size}"
            )
            with open(
                self.player_log_path, "r", encoding="utf-8", errors="ignore"
            ) as f:
                while True:
                    if current_size < self.last_log_size:
                        logger.debug(
                            "File size smaller than last log size, treating as reset."
                        )
                        self.log_storage.clear()
                        self.last_log_size = 0
                        self.load_log()
                        current_size = self.player_log_path.stat().st_size
                        continue
                    f.seek(self.last_log_size)
                    new_content = f.read()
                    logger.debug(
                        f"Read {len(new_content)} new characters from log file: {new_content[:100]}..."  # Log first 100 characters
                    )
                    if new_content.startswith("Mono path"):
                        logger.debug(
                            "New content starts with 'Mono path', reloading log."
                        )
                        self.log_storage.clear()
                        self.last_log_size = 0
                        self.load_log()
                        current_size = self.player_log_path.stat().st_size
                        continue
                    if not new_content:
                        logger.debug("No new content read from log file.")
                        # Instead of breaking, restart the debounce timer to keep monitoring
                        self._file_change_debounce_timer.start()
                        return
                    logger.debug(
                        f"Appending {len(new_content)} new characters to log content."
                    )
                    self.log_storage.append(new_content)  # Use new storage method
                    self.current_log_content = str(
                        self.log_storage
                    )  # Keep for backward compatibility
                    self.last_log_size = current_size
                    break
            self._analyze_log_content(new_content)  # Analyze only the new content
            self._update_file_info()
            self._update_statistics()
            self.apply_filter()
            self.scroll_to_end()
        except Exception as e:
            logger.error(f"Error reading appended log content: {str(e)}")
            self._file_change_debounce_timer.start()  # Restart the debounce timer on error

    file_changed_signal = Signal()

    def toggle_real_time_monitoring(self, enabled: bool) -> None:
        """Start or stop real-time monitoring of the player log file."""

        class PlayerLogEventHandler(FileSystemEventHandler, QObject):
            def __init__(self, parent: "PlayerLogTab") -> None:
                FileSystemEventHandler.__init__(self)
                QObject.__init__(self)
                self._parent = parent

            def on_modified(self, event: object) -> None:
                logger.debug(f"File modified event received: {event}")
                self._parent.file_changed_signal.emit()

        if enabled:
            self._observer = Observer()
            if (
                hasattr(self, "_observer")
                and self._observer is not None
                and self._observer.is_alive()
            ):
                logger.debug("Real-time monitoring already running.")
                return
            if self.player_log_path is None:
                show_warning("Player log path is not set.")
                self.real_time_monitor_checkbox.setChecked(False)
                return
            # Stop existing observer if any before creating a new one
            if hasattr(self, "_observer") and self._observer is not None:
                if self._observer.is_alive():
                    logger.debug("Stopping existing observer before starting new one.")
                    self._observer.stop()
                    self._observer.join()
            event_handler = PlayerLogEventHandler(self)
            self.file_changed_signal.connect(self.on_file_changed)
            try:
                self._observer.schedule(
                    event_handler, str(self.player_log_path.parent), recursive=False
                )
                self._observer.start()
                logger.info(
                    f"Started real-time monitoring of Player.log at {self.player_log_path}"
                )
            except Exception as e:
                logger.error(f"Failed to start observer: {e}")
                show_warning(f"Failed to start real-time monitoring: {e}")
                self.real_time_monitor_checkbox.setChecked(False)
        else:
            if (
                hasattr(self, "_observer")
                and self._observer is not None
                and self._observer.is_alive()
            ):
                self._observer.stop()
                self._observer.join()
                logger.info("Stopped real-time monitoring of Player.log.")

    def load_log(self, chunk_size: int = 1024) -> None:
        """Load the player log file content in chunks for lazy loading."""
        if self.player_log_path is None or not self.player_log_path.exists():
            show_warning("Player log file does not exist.")
            return
        try:
            self.log_storage.clear()  # Clear previous content
            self.log_stats = {
                "total_lines": 0,
                "infos": 0,
                "keybinds": 0,
                "mod_issues": 0,
                "warnings": 0,
                "errors": 0,
                "exceptions": 0,
            }
            with open(
                self.player_log_path, "r", encoding="utf-8", errors="ignore"
            ) as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    self.log_storage.append(chunk)  # Use new storage method
                    self._analyze_log_content(chunk)  # Analyze each chunk as it's read
            self.last_log_size = len(self.log_storage)  # Update based on new storage
            self.current_log_content = str(
                self.log_storage
            )  # Keep for backward compatibility
            self._update_file_info()
            self._update_statistics()
            self.apply_filter()
            self.scroll_to_end()
            logger.info(
                "Loaded player log file in chunks using memory-efficient storage."
            )
        except Exception as e:
            logger.error(f"Failed to load player log file: {e}")

    def _update_file_info(self) -> None:
        """Update the file info labels with path, size, and last modified date."""
        if self.player_log_path is None:
            # Show info for logs loaded from URL
            if self.current_log_content:
                url = self.url
                if url:
                    self.file_path_label.setText(
                        self.tr("Path: Loaded from URL: {url}").format(url=url)
                    )
                else:
                    self.file_path_label.setText(self.tr("Path: Loaded from URL"))
                self.file_size_label.setText(
                    self.tr("Size: {size:,} bytes").format(
                        size=len(self.current_log_content)
                    )
                )
                self.last_modified_label.setText(self.tr("Modified: N/A"))
            else:
                self.file_path_label.setText(self.tr("Path: N/A"))
                self.file_size_label.setText(self.tr("Size: N/A"))
                self.last_modified_label.setText(self.tr("Modified: N/A"))
            return
        if not self.player_log_path.exists():
            self.file_path_label.setText(self.tr("Path: N/A"))
            self.file_size_label.setText(self.tr("Size: N/A"))
            self.last_modified_label.setText(self.tr("Modified: N/A"))
            return
        try:
            path_str = str(self.player_log_path)
            size_bytes = self.player_log_path.stat().st_size
            modified_time = self.player_log_path.stat().st_mtime

            # Format size in human-readable form
            def format_size(size: float) -> str:
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if size < 1024:
                        return f"{size:.1f} {unit}"
                    size /= 1024
                return f"{size:.1f} PB"

            size_str = format_size(size_bytes)
            modified_str = datetime.fromtimestamp(modified_time).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            self.file_path_label.setText(
                self.tr("Path: {path_str}").format(path_str=path_str)
            )
            self.file_size_label.setText(
                self.tr("Size: {size_str}").format(size_str=size_str)
            )
            self.last_modified_label.setText(
                self.tr("Modified: {modified_str}").format(modified_str=modified_str)
            )
        except Exception as e:
            logger.error(f"Failed to update file info: {e}")

    def _update_match_count(self) -> None:
        """Update the match count label based on current matches."""
        total_matches = len(self.matches)
        current_index = (
            self.current_match_index + 1 if self.current_match_index >= 0 else 0
        )
        self.match_count_label.setText(f"{current_index}/{total_matches}")

    def _on_search_text_changed_debounced(self) -> None:
        self._search_debounce_timer.start()

    def _do_search_text_changed(self) -> None:
        self.search_text_changed(self.search_input.text() if self.search_input else "")

    def search_text_changed(self, text: str) -> None:
        self.highlighter.set_search_term(text)
        self.matches.clear()
        self.current_match_index = -1
        if not text:
            self._update_match_count()
            return
        cursor = self.log_display.textCursor()
        document = self.log_display.document()
        regex = QRegularExpression(
            text, QRegularExpression.PatternOption.CaseInsensitiveOption
        )
        pos = 0
        while True:
            match = regex.match(document.toPlainText(), pos)
            if not match.hasMatch():
                break
            start = match.capturedStart()
            end = match.capturedEnd()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            self.matches.append(QTextCursor(cursor))
            pos = end
        if self.matches:
            self.current_match_index = 0
            self.log_display.setTextCursor(self.matches[0])
        self._update_match_count()

    def goto_previous_match(self) -> None:
        if not self.matches:
            return
        self.current_match_index = (self.current_match_index - 1) % len(self.matches)
        if self.current_match_index < 0:
            self.current_match_index = (
                len(self.matches) - 1
            )  # Wrap around to last match
        self.log_display.setTextCursor(self.matches[self.current_match_index])
        self._update_match_count()

    def goto_next_match(self) -> None:
        if not self.matches:
            return
        self.current_match_index = (self.current_match_index + 1) % len(self.matches)
        self.log_display.setTextCursor(self.matches[self.current_match_index])
        self._update_match_count()

    def _get_cached_regex(self, pattern: str) -> QRegularExpression:
        """Get a cached regex object or create and cache a new one."""
        if pattern not in self._pattern_regex_cache:
            self._pattern_regex_cache[pattern] = QRegularExpression(
                pattern, QRegularExpression.PatternOption.CaseInsensitiveOption
            )
        return self._pattern_regex_cache[pattern]

    def _get_cached_matches(self, pattern: str) -> List[QTextCursor]:
        """Get cached matches for a pattern or find and cache them."""
        if pattern not in self._pattern_matches_cache:
            regex = self._get_cached_regex(pattern)
            document = self.log_display.document()
            plain_text = document.toPlainText()

            matches = []
            it = regex.globalMatch(plain_text)
            while it.hasNext():
                match = it.next()
                if match.hasMatch():
                    cursor = QTextCursor(document)
                    cursor.setPosition(match.capturedStart())
                    cursor.setPosition(
                        match.capturedEnd(), QTextCursor.MoveMode.KeepAnchor
                    )
                    matches.append(QTextCursor(cursor))

            self._pattern_matches_cache[pattern] = matches

        return self._pattern_matches_cache[pattern]

    def _clear_pattern_cache(self, pattern: Optional[str] = None) -> None:
        """Clear cached matches for a specific pattern or all patterns."""
        if pattern:
            self._pattern_matches_cache.pop(pattern, None)
        else:
            self._pattern_matches_cache.clear()

    def goto_previous_pattern(self, pattern: str) -> None:
        """Navigate to the previous occurrence of the pattern with caching and wrapping."""
        if not pattern:
            return
        try:
            matches = self._get_cached_matches(pattern)
            if not matches:
                return

            current_cursor = self.log_display.textCursor()
            current_pos = current_cursor.position()

            # Find the previous match (closest match before current position)
            prev_match = None
            for i in range(len(matches) - 1, -1, -1):
                match_cursor = matches[i]
                if match_cursor.selectionStart() < current_pos:
                    prev_match = match_cursor
                    break

            # wrap around to the last match, If no previous match found (cursor is before first match or at start)
            if prev_match is None and matches:
                prev_match = matches[-1]

            if prev_match:
                self.log_display.setTextCursor(QTextCursor(prev_match))
                self.log_display.ensureCursorVisible()

                # Update visual feedback
                self._update_navigation_feedback(pattern, len(matches))

        except Exception as e:
            logger.error(f"Error in goto_previous_pattern: {e}")
            self._clear_pattern_cache(pattern)

    def goto_next_pattern(self, pattern: str) -> None:
        """Navigate to the next occurrence of the pattern with caching and wrapping."""
        try:
            matches = self._get_cached_matches(pattern)
            if not matches:
                return

            current_cursor = self.log_display.textCursor()
            current_pos = current_cursor.position()

            # Find the next match
            next_match = None
            for match_cursor in matches:
                if match_cursor.selectionStart() > current_pos:
                    next_match = match_cursor
                    break

            # If no next match found, wrap around to the first match
            if next_match is None and matches:
                next_match = matches[0]

            if next_match:
                self.log_display.setTextCursor(QTextCursor(next_match))
                self.log_display.ensureCursorVisible()

                # Update visual feedback
                self._update_navigation_feedback(pattern, len(matches))

        except Exception as e:
            logger.error(f"Error in goto_next_pattern: {e}")
            self._clear_pattern_cache(pattern)

    def _update_navigation_feedback(self, pattern: str, total_matches: int) -> None:
        """Update visual feedback for navigation."""
        # Highlight the current match temporarily
        cursor = self.log_display.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(self.quick_nav_highlight_format)

        # Update status message (optional - could be shown in a status bar)
        logger.debug(
            f"Navigated to pattern '{pattern}' - {total_matches} total matches"
        )

    def load_default_log(self) -> None:
        self.player_log_path = self._get_player_log_path()
        if self.player_log_path is None:
            show_warning(self.tr("Player log file not found."))
            return
        self.load_log()

    def load_log_from_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Log File", "", "Log Files (*.log *.txt);;All Files (*)"
        )
        if file_path:
            self.player_log_path = Path(file_path)
            self.load_log()

    def load_log_from_link(self) -> None:
        url, ok = QInputDialog.getText(
            self, self.tr("Load Log from Link"), self.tr("Enter URL:")
        )
        if ok and url:
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                self.current_log_content = resp.text
                self.player_log_path = None  # Not a file
                self.url = url
                self._analyze_log_content(self.log_storage.get_full_content())
                self._update_file_info()
                self._update_statistics()
                self.apply_filter()
                self.scroll_to_end()
                show_information(
                    title=self.tr("Log loaded successfully from URL"),
                    text=f"{url}",
                )
            except Exception as e:
                show_warning(
                    title=self.tr("Failed to load log from URL"),
                    text=self.tr("Failed due to error: {error}").format(error=e),
                )

    def refresh_log(self) -> None:
        self.load_log()

    def export_log(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Log", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.filtered_content)
                show_information(f"Log exported to {file_path}")
            except OSError as e:
                show_warning(f"Failed to export log: {e.strerror}")
            except Exception as e:
                show_warning(f"Failed to export log: {type(e).__name__}: {e}")

    def show_context_menu(self, pos: QPoint) -> None:
        menu = self.log_display.createStandardContextMenu()
        cursor = self.log_display.cursorForPosition(pos)
        line_number = cursor.blockNumber()
        bookmark_action_text = (
            "Remove Bookmark"
            if line_number in self.bookmarked_lines
            else "Add Bookmark"
        )
        bookmark_action = menu.addAction(bookmark_action_text)
        bookmark_action.triggered.connect(lambda: self.toggle_bookmark(line_number))
        pathmatch = LogPatternManager.PATHLIKE_PATTERN.findall(cursor.block().text())
        if pathmatch:
            for path in pathmatch:
                for candidate in (
                    path,
                    path[:-1],
                ):  # error messages frequently tag on a ] or other terminator character
                    if os.path.exists(candidate):
                        menu.addAction(
                            f"Open '{candidate}'", lambda p=candidate: self.open_file(p)
                        )
                        break
        menu.exec(self.log_display.mapToGlobal(pos))

    def open_file(self, file_path: str) -> None:
        if self.settings_controller.settings.text_editor_location:
            launch_process(
                self.settings_controller.settings.text_editor_location,
                self.settings_controller.settings.text_editor_file_arg.split(" ")
                + [file_path],
                str(AppInfo().application_folder),
            )

    def toggle_bookmark(self, line_number: int) -> None:
        if line_number in self.bookmarked_lines:
            self.bookmarked_lines.remove(line_number)
        else:
            self.bookmarked_lines.add(line_number)
        self.highlight_bookmarks()

    def highlight_bookmarks(self) -> None:
        """Highlight only changed bookmark lines for efficiency."""
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#FFD700"))  # Gold color for bookmarks
        clear_fmt = QTextCharFormat()
        clear_fmt.setBackground(QColor("transparent"))
        doc = self.log_display.document()
        # Only update lines that are bookmarked
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            if i in self.bookmarked_lines:
                cursor.setCharFormat(fmt)
            else:
                cursor.setCharFormat(clear_fmt)

    def _analyze_log_content(self, new_content: str) -> None:
        """Analyze the log content and update statistics more efficiently."""
        lines = new_content.splitlines()
        self.log_stats["total_lines"] += len(lines)

        # Use LogPatternManager patterns for consistency
        for line in lines:
            if LogPatternManager.INFO_FILTER_PATTERN.search(line):
                self.log_stats["infos"] += 1
            if LogPatternManager.KEYBIND_FILTER_PATTERN.search(line):
                self.log_stats["keybinds"] += 1
            if LogPatternManager.MOD_ISSUE_FILTER_PATTERN.search(line):
                self.log_stats["mod_issues"] += 1
            if LogPatternManager.WARNING_FILTER_PATTERN.search(line):
                self.log_stats["warnings"] += 1
            if LogPatternManager.ERROR_FILTER_PATTERN.search(line):
                self.log_stats["errors"] += 1
            if LogPatternManager.EXCEPTION_FILTER_PATTERN.search(line):
                self.log_stats["exceptions"] += 1

    def apply_filter(self) -> None:
        """Apply the selected filter and mod name filter to the log content more efficiently."""
        filter_text = (
            self.filter_combo.currentText() if self.filter_combo else "All Entries"
        )
        mod_filter = self.mod_filter_input.text() if self.mod_filter_input else ""
        lines = self.current_log_content.splitlines()
        filtered_lines = []

        # Precompile combined patterns for filters
        keybind_pattern = self._keybind_pattern
        mod_issue_pattern = self._mod_issue_pattern
        warning_pattern = self._warning_pattern
        error_pattern = self._error_pattern
        exception_pattern = self._exception_pattern

        for line in lines:
            if mod_filter and mod_filter.lower() not in line.lower():
                continue
            if filter_text == self.tr("All Entries"):
                filtered_lines.append(line)
            elif filter_text == self.tr("Infos Only") and self._info_pattern.search(
                line
            ):
                filtered_lines.append(line)
            elif filter_text == self.tr("Keybinds Only") and keybind_pattern.search(
                line
            ):
                filtered_lines.append(line)
            elif filter_text == self.tr("Mod Issues") and mod_issue_pattern.search(
                line
            ):
                filtered_lines.append(line)
            elif filter_text == self.tr("Warnings Only") and warning_pattern.search(
                line
            ):
                filtered_lines.append(line)
            elif filter_text == self.tr("Errors Only") and error_pattern.search(line):
                filtered_lines.append(line)
            elif filter_text == self.tr("Exceptions Only") and exception_pattern.search(
                line
            ):
                filtered_lines.append(line)
            elif filter_text == self.tr("All Issues") and (
                keybind_pattern.search(line)
                or mod_issue_pattern.search(line)
                or warning_pattern.search(line)
                or error_pattern.search(line)
                or exception_pattern.search(line)
            ):
                filtered_lines.append(line)
        # Collapse repeated lines before displaying
        collapsed_lines = self._collapse_repeated_lines(filtered_lines)
        self.filtered_content = "\n".join(collapsed_lines)
        self.log_display.setPlainText(self.filtered_content)
        self._update_match_count()

        # Optimize the statistics update
        self._update_statistics()

    def _update_statistics(self) -> None:
        """Update the statistics labels in the UI (consolidated)."""
        # Update button texts for clickable stats
        self.total_lines_label.setText(
            self.tr("Total Lines: {total_lines}").format(
                total_lines=self.log_stats["total_lines"]
            )
        )
        self.info_label.setText(
            self.tr("Infos: {infos}").format(infos=self.log_stats["infos"])
        )
        self.keybind_label.setText(
            self.tr("Keybinds: {keybinds}").format(keybinds=self.log_stats["keybinds"])
        )
        self.mod_issues_label.setText(
            self.tr("Mod Issues: {mod_issues}").format(
                mod_issues=self.log_stats["mod_issues"]
            )
        )
        self.warnings_label.setText(
            self.tr("Warnings: {warnings}").format(warnings=self.log_stats["warnings"])
        )
        self.errors_label.setText(
            self.tr("Errors: {errors}").format(errors=self.log_stats["errors"])
        )
        self.exceptions_label.setText(
            self.tr("Exceptions: {exceptions}").format(
                exceptions=self.log_stats["exceptions"]
            )
        )
        self.all_issues_label.setText(
            self.tr("All Issues: {all_issues}").format(
                all_issues=self.log_stats["errors"]
                + self.log_stats["warnings"]
                + self.log_stats["exceptions"]
                + self.log_stats["mod_issues"]
                + self.log_stats["keybinds"]
            )
        )
