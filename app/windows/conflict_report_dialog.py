"""On-demand conflict report for a captured active mod list."""

from collections.abc import Callable
from string import Formatter
from typing import Any
from uuid import uuid4

from PySide6.QtCore import (
    QT_TRANSLATE_NOOP,
    QCoreApplication,
    QLocale,
    QModelIndex,
    QSignalBlocker,
    Qt,
    Slot,
)
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStyle,
    QTableView,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.controllers.metadata_controller import MetadataController
from app.models.conflict_report import (
    ConflictModModel,
    ConflictReportBrowser,
    ConflictTableModel,
    FindingFilters,
    FindingView,
)
from app.models.conflict_report import (
    safe_text as _safe_text,
)
from app.services.conflict_detector_runner import ConflictDetectorRunner
from app.services.conflict_snapshot import ScanSnapshot, snapshot_active_mods
from app.utils.event_bus import EventBus
from app.views.conflict_report_details import FindingInspector, ScanNotesView
from app.views.mods_panel import ModListWidget

_INVALID_INDEX = QModelIndex()
_SEVERITY_ORDER = ("error", "warning", "info")
_ALL_SEVERITIES = frozenset(_SEVERITY_ORDER)


def _template_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _, field, spec, conversion in Formatter().parse(template):
        if field is not None:
            if not field.isidentifier() or spec or conversion is not None:
                raise ValueError("Invalid diagnostic field")
            fields.add(field)
    return fields


def _diagnostic_message(diagnostic: dict[str, Any]) -> str:
    templates = {
        "about_parse_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Failed to parse mod at {path}: {detail}"
        ),
        "load_after_violation": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "'{mod}' declares loadAfter '{dependency}' but is loaded before it",
        ),
        "load_before_violation": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "'{mod}' declares loadBefore '{dependency}' but is loaded after it",
        ),
        "force_load_after_violation": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "'{mod}' declares forceLoadAfter '{dependency}' but is loaded before it (hard constraint violated)",
        ),
        "force_load_before_violation": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "'{mod}' declares forceLoadBefore '{dependency}' but is loaded after it (hard constraint violated)",
        ),
        "xml_abstract_defs_skipped": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Skipped {count} abstract def(s) without a usable defName",
        ),
        "xml_unnamed_defs_skipped": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Skipped {count} def(s) without defName (unindexable; RimWorld auto-names these at runtime)",
        ),
        "manual_dll_read_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Failed to read DLL for manual patch detection {path}: {detail}",
        ),
        "manual_dll_scan_panic": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Manual patch detection panicked while scanning {path} (caught; results for this DLL may be incomplete)",
        ),
        "manual_patch_hint": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Possible manual patch hint in {dll}: {method} (best-effort heuristic, may be a false positive)",
        ),
        "harmony_parse_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Failed to parse Harmony patches from {dll}: {detail}",
        ),
        "harmony_parse_panic": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "DLL parser panicked while parsing {dll} (dotnetdll crash caught)",
        ),
        "invalid_game_version": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Invalid game version {version_debug}; falling back to default folder selection",
        ),
        "unknown_config_fields": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Unknown config fields ignored: {fields}"
        ),
        "mod_directory_missing": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Mod directory does not exist: {path}"
        ),
        "mod_directory_not_directory": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Mod directory is not a directory: {path}"
        ),
        "mods_config_parse_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Failed to parse ModsConfig.xml: {detail}"
        ),
        "active_mod_not_found": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Mod '{package_id}' not found in search directories (a mod folder may have failed to parse — see \"Failed to parse mod at\" diagnostics in this report)",
        ),
        "load_folders_parse_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Failed to parse LoadFolders.xml; using implicit folder resolution: {detail}",
        ),
        "load_folders_unknown_conditions": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Unknown LoadFolders.xml condition attributes: {conditions}",
        ),
        "load_folders_inspection_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Failed to inspect LoadFolders.xml in {path}; using implicit folder resolution: {detail}",
        ),
        "content_directory_inspection_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Failed to inspect content directory {path}: {detail}",
        ),
        "content_path_not_directory": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Failed to inspect content directory {path}: not a directory",
        ),
        "load_folders_empty": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "LoadFolders.xml selected no folders"
        ),
        "load_folders_empty_invalid_paths": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "LoadFolders.xml selected no folders; invalid paths skipped: {paths}",
        ),
        "load_folders_invalid_paths": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Invalid LoadFolders.xml folder paths skipped: {paths}",
        ),
        "load_folders_no_applicable_version": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "No applicable LoadFolders.xml version entry; using implicit folder resolution",
        ),
        "content_symlink_skipped": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Skipped symlink {path}"
        ),
        "content_enumeration_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Failed to enumerate {path}: {detail}"
        ),
        "mod_directory_read_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Failed to read directory {path}: {detail}"
        ),
        "mod_directory_entry_read_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Failed to read directory entry in {path}: {detail}",
        ),
        "xml_read_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Failed to read {path}: {detail}"
        ),
        "xml_parse_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "XML parse error in {path}: {detail}"
        ),
        "xml_unclosed_elements": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "XML parse error in {path}: document ends with {count} unclosed element(s) (results may be incomplete)",
        ),
        "xml_def_name_decode_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "defName in {path} could not be decoded: {detail}",
        ),
        "xml_def_name_unexpected_close": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "defName in {path} closed by unexpected </{tag}>; def dropped",
        ),
        "xml_def_name_unclosed": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "defName in {path} is not closed; def dropped"
        ),
        "xml_def_name_nested": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "defName in {path} contains nested markup; defName is a leaf: def dropped",
        ),
        "xml_patch_depth_exceeded": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Patch operation nesting exceeds maximum depth {depth} in {path}; skipping operation",
        ),
        "xml_text_decode_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Malformed <{element}> text in {path}: {detail}",
        ),
        "xml_text_nested": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Nested element in <{element}> text in {path}"
        ),
        "xml_text_mismatched": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Mismatched element in <{element}> text in {path}",
        ),
        "xml_text_mismatched_end": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "Mismatched end element in <{element}> text in {path}",
        ),
        "xml_text_unexpected_eof": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic", "Unexpected EOF in <{element}> text in {path}"
        ),
        "xml_reconstruction_parse_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "internal XML reconstruction error for {def_id}: {detail}",
        ),
        "xml_reconstruction_text_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "internal XML reconstruction error for {def_id}: text decode failed: {detail}",
        ),
        "xml_reconstruction_attribute_failure": QT_TRANSLATE_NOOP(
            "ConflictDetectorDiagnostic",
            "internal XML reconstruction error for {def_id}: attribute decode failed: {detail}",
        ),
    }
    code = diagnostic.get("code")
    source = templates.get(code) if isinstance(code, str) else None
    if isinstance(source, str):
        try:
            required = _template_fields(source)
            params = diagnostic.get("params", {})
            if not isinstance(params, dict) or not required <= params.keys():
                return diagnostic["message"]
            template = QCoreApplication.translate("ConflictDetectorDiagnostic", source)
            if _template_fields(template) != required:
                return diagnostic["message"]
            return template.format(**params)
        except KeyError, ValueError, IndexError, AttributeError, TypeError:
            pass
    return diagnostic["message"]


class ConflictReportDialog(QDialog):
    def __init__(
        self,
        active_list: ModListWidget,
        metadata_controller: MetadataController,
        instance_id: Callable[[], str],
        snapshot: ScanSnapshot,
        runner: ConflictDetectorRunner | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.active_list = active_list
        self.metadata_controller = metadata_controller
        self.instance_id = instance_id
        self.snapshot = snapshot
        self.runner = runner if runner is not None else ConflictDetectorRunner(self)
        self.request_id = str(uuid4())
        self.report: dict[str, Any] = {}
        self.state = "running"
        self.is_stale = False
        self.is_incomplete = bool(snapshot.issues) or snapshot.game_version is None
        self.browser = ConflictReportBrowser(self)
        self._pending_selected_visible_row: int | None = None
        self._teardown_complete = False

        self.setWindowTitle(self.tr("Mod Conflict Report"))

        self.status_label = self._make_label()
        self.context_label = self._make_label(word_wrap=True)
        self.context_label.setText(
            self.tr(
                "Best effort only; undetected conflicts and disk changes are possible."
            )
        )
        self.version_label = self._make_label()
        self.instance_label = self._make_label()
        self.summary_label = self._make_label(word_wrap=True)
        self.result_label = self._make_label(word_wrap=True)
        self.empty_label = self._make_label(word_wrap=True)
        self.empty_label.setVisible(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)

        self.conflict_model = ConflictTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.conflict_model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(
            self.fontMetrics().lineSpacing() * 2 + 8
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, self._severity_column_width())
        self.table.selectionModel().currentRowChanged.connect(self._select_finding)

        self.inspector = FindingInspector()
        self.inspector.mod_requested.connect(self.set_mod_filter)
        self.notes = ScanNotesView(_diagnostic_message)
        self.notes.model.prepared.connect(self._notes_prepared)
        self.notes.model.busy_changed.connect(self._notes_busy_changed)
        self.incomplete_badge = QToolButton()
        self.incomplete_badge.clicked.connect(self._open_notes)

        self.mod_model = ConflictModModel(self)
        self.mod_table = QTableView()
        self.mod_table.setModel(self.mod_model)
        self.mod_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.mod_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.mod_table.setAlternatingRowColors(True)
        self.mod_table.verticalHeader().setVisible(False)
        self.mod_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for section in (1, 2, 3):
            self.mod_table.horizontalHeader().setSectionResizeMode(
                section, QHeaderView.ResizeMode.ResizeToContents
            )
        self.mod_table.selectionModel().currentRowChanged.connect(
            self._mod_selection_changed
        )

        self.mod_filter_label = self._make_label(word_wrap=True)
        self.mod_filter_label.setVisible(False)
        self._clear_mod_filter_button = QToolButton()
        self._clear_mod_filter_button.setText("×")
        self._clear_mod_filter_button.setToolTip(self.tr("Clear mod filter"))
        self._clear_mod_filter_button.clicked.connect(lambda: self.set_mod_filter(None))
        self._clear_mod_filter_button.setVisible(False)

        self.mod_search = QLineEdit()
        self.mod_search.setPlaceholderText(self.tr("Search mods"))
        self.mod_search.textChanged.connect(self._apply_mod_search)

        self.finding_search = QLineEdit()
        self.finding_search.setPlaceholderText(self.tr("Search findings"))
        self.finding_search.textChanged.connect(self._apply_search_filters)

        self.type_filter = QComboBox()
        self.type_filter.addItem(self.tr("All types"), None)
        self.type_filter.addItem(self.tr("Def"), "def")
        self.type_filter.addItem(self.tr("Harmony"), "harmony")
        self.type_filter.currentIndexChanged.connect(self._apply_type_filter)

        self.severity_buttons = self._build_severity_buttons()
        self.reset_filters_button = QPushButton(self.tr("Reset filters"))
        self.reset_filters_button.clicked.connect(self._reset_filters)

        self.cancel_button = QPushButton(self.tr("Cancel scan"))
        self.cancel_button.clicked.connect(self.cancel_scan)
        close_button = QPushButton(self.tr("Close"))
        close_button.clicked.connect(self.close)

        findings_controls = QHBoxLayout()
        findings_controls.addWidget(self.severity_buttons["all"])
        for severity in _SEVERITY_ORDER:
            findings_controls.addWidget(self.severity_buttons[severity])
        findings_controls.addStretch(1)

        mod_filter_row = QHBoxLayout()
        mod_filter_row.setContentsMargins(0, 0, 0, 0)
        mod_filter_row.addWidget(self.mod_filter_label)
        mod_filter_row.addWidget(self._clear_mod_filter_button)
        mod_filter_row.addStretch(1)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.addWidget(self._make_section_label(self.tr("Finding search")))
        sidebar_layout.addWidget(self.finding_search)
        sidebar_layout.addWidget(self._make_section_label(self.tr("Finding type")))
        sidebar_layout.addWidget(self.type_filter)
        sidebar_layout.addWidget(self.reset_filters_button)
        sidebar_layout.addWidget(self._make_section_label(self.tr("Active mod filter")))
        sidebar_layout.addLayout(mod_filter_row)
        sidebar_layout.addWidget(self._make_section_label(self.tr("Affected mods")))
        sidebar_layout.addWidget(self.mod_search)
        sidebar_layout.addWidget(self.mod_table)

        findings_splitter = QSplitter(Qt.Orientation.Horizontal)
        findings_splitter.setChildrenCollapsible(False)
        findings_splitter.addWidget(sidebar)
        findings_splitter.addWidget(self.table)
        findings_splitter.addWidget(self.inspector)
        findings_splitter.setStretchFactor(0, 1)
        findings_splitter.setStretchFactor(1, 3)
        findings_splitter.setStretchFactor(2, 2)

        findings_tab = QWidget()
        findings_layout = QVBoxLayout(findings_tab)
        findings_layout.addWidget(self.summary_label)
        findings_layout.addLayout(findings_controls)
        findings_layout.addWidget(self.result_label)
        findings_layout.addWidget(self.empty_label)
        findings_layout.addWidget(findings_splitter, 1)

        self.tabs = QTabWidget()
        self.tabs.addTab(findings_tab, self.tr("Findings"))
        self._notes_tab_index = self.tabs.addTab(self.notes, self.tr("Scan notes"))

        buttons = QHBoxLayout()
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        for widget in (
            self.status_label,
            self.incomplete_badge,
            self.context_label,
            self.instance_label,
            self.version_label,
            self.progress_bar,
            self.tabs,
        ):
            layout.addWidget(widget)
        layout.addLayout(buttons)

        self._resize_for_screen()
        self._update_snapshot_labels()
        self._show_diagnostics([])
        self._update_severity_button_texts(
            {severity: 0 for severity in _SEVERITY_ORDER}
        )
        self._update_mod_filter_label(None)
        self._update_findings_feedback()
        self._connect_invalidation()
        self.browser.prepared.connect(self._browser_prepared)
        self.browser.busy_changed.connect(self._browser_busy_changed)
        self.browser.applied.connect(self._apply_view)
        self.runner.progress.connect(self._progress)
        self.runner.succeeded.connect(self._succeeded)
        self.runner.failed.connect(self._failed)
        self.runner.cancelled.connect(self._cancelled)

        if not snapshot.mod_paths:
            self.state = "no_input"
            self._update_findings_feedback()
            self._update_status()
            return
        config: dict[str, object] = {
            "mod_paths": list(snapshot.mod_paths),
            "ordered": True,
        }
        if snapshot.game_version is not None:
            config["game_version"] = snapshot.game_version
        self._update_status()
        self.runner.start({"protocol": 1, "id": self.request_id, "config": config})

    def _resize_for_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.resize(900, 650)
            return
        available = screen.availableGeometry().size()
        minimum = self.minimumSizeHint()
        minimum_width = min(minimum.width(), available.width())
        minimum_height = min(minimum.height(), available.height())
        self.setMinimumSize(minimum_width, minimum_height)
        target_width = max(900, int(available.width() * 0.82), minimum_width)
        target_height = max(650, int(available.height() * 0.8), minimum_height)
        self.resize(
            min(target_width, available.width()),
            min(target_height, available.height()),
        )

    def _severity_column_width(self) -> int:
        text_width = max(
            self.fontMetrics().horizontalAdvance(self.tr("Warning")),
            self.fontMetrics().horizontalAdvance(self.tr("Severity")),
        )
        return max(96, min(text_width + 48, 180))

    def _make_label(self, *, word_wrap: bool = False) -> QLabel:
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(word_wrap)
        return label

    def _make_section_label(self, text: str) -> QLabel:
        label = self._make_label()
        label.setText(text)
        return label

    def _build_severity_buttons(self) -> dict[str, QToolButton]:
        buttons: dict[str, QToolButton] = {}
        buttons["all"] = self._make_filter_button(self.tr("All"))
        buttons["all"].clicked.connect(self._select_all_severities)
        icons = {
            "error": self.style().standardIcon(
                QStyle.StandardPixmap.SP_MessageBoxCritical
            ),
            "warning": self.style().standardIcon(
                QStyle.StandardPixmap.SP_MessageBoxWarning
            ),
            "info": self.style().standardIcon(
                QStyle.StandardPixmap.SP_MessageBoxInformation
            ),
        }
        for severity, label in (
            ("error", self.tr("Errors")),
            ("warning", self.tr("Warnings")),
            ("info", self.tr("Info")),
        ):
            button = self._make_filter_button(label)
            button.setCheckable(True)
            button.setChecked(severity == "error")
            button.setIcon(icons[severity])
            button.clicked.connect(self._apply_severity_filters)
            buttons[severity] = button
        return buttons

    def _make_filter_button(self, text: str) -> QToolButton:
        button = QToolButton()
        button.setCheckable(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setText(text)
        return button

    def _connect_invalidation(self) -> None:
        model = self.active_list.model()
        for signal in (
            model.rowsInserted,
            model.rowsRemoved,
            model.rowsMoved,
            model.modelReset,
            model.layoutChanged,
            model.dataChanged,
        ):
            signal.connect(self._mark_stale)
        EventBus().do_activate_current_instance.connect(self._mark_stale)
        self.metadata_controller.metadata_refresh_started.connect(self._mark_stale)
        self.metadata_controller.metadata_refreshed.connect(self._metadata_refreshed)
        for signal in (
            self.metadata_controller.mod_created_signal,
            self.metadata_controller.mod_deleted_signal,
            self.metadata_controller.mod_metadata_updated_signal,
        ):
            signal.connect(self._mark_stale)

    @Slot()
    def _mark_stale(self, *_args: object) -> None:
        self.is_stale = True
        self._update_status()

    @Slot()
    def _check_snapshot(self, *_args: object) -> None:
        current = snapshot_active_mods(
            self.active_list, self.metadata_controller, self.instance_id()
        )
        if current != self.snapshot:
            self._mark_stale()

    @Slot()
    def _metadata_refreshed(self) -> None:
        self._check_snapshot()
        self._mark_stale()

    def _update_snapshot_labels(self) -> None:
        self.version_label.setText(
            self.tr("Game version: {version}").format(
                version=_safe_text(
                    self.snapshot.game_version
                    if self.snapshot.game_version is not None
                    else self.tr("Unknown")
                )
            )
        )
        self.instance_label.setText(
            self.tr("Instance: {instance}; usable mods: {count}").format(
                instance=_safe_text(self.snapshot.instance_id),
                count=self._format_count(len(self.snapshot.mod_paths)),
            )
        )

    def _update_status(self) -> None:
        states = {
            "running": self.tr("Scanning…"),
            "cancelled": self.tr("Scan cancelled"),
            "failed": self.tr("Scan failed"),
            "no_input": self.tr("No usable mod inputs"),
            "finished": self.tr("Scan finished"),
        }
        parts = [states[self.state]]
        if self.is_incomplete:
            parts.append(self.tr("Incomplete input or analysis"))
        if self.is_stale:
            parts.append(self.tr("Stale: the active snapshot may have changed"))
        self.status_label.setText(" — ".join(parts))
        self._update_notes_badge()
        self.cancel_button.setEnabled(self.state == "running")
        self.progress_bar.setVisible(self.state == "running")

    def _show_diagnostics(
        self, diagnostics: list[dict[str, Any]], error: str = ""
    ) -> None:
        self.notes.set_notes(self.snapshot, diagnostics, error)

    def _open_notes(self) -> None:
        self.tabs.setCurrentWidget(self.notes)

    def _notes_busy_changed(self, _busy: bool) -> None:
        if not self._teardown_complete:
            self._update_notes_badge()

    def _notes_prepared(self) -> None:
        if not self._teardown_complete:
            self.is_incomplete = self.notes.model.incomplete
            self._update_status()

    def _update_notes_badge(self) -> None:
        count = self.notes.model.attention_count
        if count is None:
            self.tabs.setTabText(
                self._notes_tab_index,
                self.tr("Scan notes: {count}").format(count="…"),
            )
            self.incomplete_badge.setText(self.tr("Preparing scan notes (…)"))
        else:
            formatted_count = self._format_count(count)
            self.tabs.setTabText(
                self._notes_tab_index,
                self.tr("Scan notes: {count}").format(count=formatted_count),
            )
            self.incomplete_badge.setText(
                self.tr("Incomplete input or analysis — scan notes ({count})").format(
                    count=formatted_count
                )
            )
        self.incomplete_badge.setVisible(self.is_incomplete or count is None)

    def _format_count(self, count: int) -> str:
        return QLocale().toString(count)

    def _update_summary(self, report: dict[str, Any]) -> None:
        summary = report["summary"]
        counts = summary["conflicts_by_severity"]
        self.summary_label.setText(
            self.tr(
                "Parsed mods: {total}; Mods with conflicts: {affected}; Errors: {errors}; Warnings: {warnings}; Info: {info}"
            ).format(
                total=self._format_count(summary["total_mods"]),
                affected=self._format_count(summary["mods_with_conflicts"]),
                errors=self._format_count(counts["error"]),
                warnings=self._format_count(counts["warning"]),
                info=self._format_count(counts["info"]),
            )
        )
        self._update_severity_button_texts(counts)

    def _update_severity_button_texts(self, counts: dict[str, int]) -> None:
        total = sum(counts.values())
        self.severity_buttons["all"].setText(
            self.tr("All ({count})").format(count=self._format_count(total))
        )
        self.severity_buttons["error"].setText(
            self.tr("Errors ({count})").format(
                count=self._format_count(counts.get("error", 0))
            )
        )
        self.severity_buttons["warning"].setText(
            self.tr("Warnings ({count})").format(
                count=self._format_count(counts.get("warning", 0))
            )
        )
        self.severity_buttons["info"].setText(
            self.tr("Info ({count})").format(
                count=self._format_count(counts.get("info", 0))
            )
        )

    def _set_severity_selection(self, severities: frozenset[str]) -> None:
        blockers = [QSignalBlocker(button) for button in self.severity_buttons.values()]
        with_all = severities == _ALL_SEVERITIES
        for severity in _SEVERITY_ORDER:
            self.severity_buttons[severity].setChecked(severity in severities)
        self.severity_buttons["all"].setChecked(with_all)
        del blockers

    def _current_severities(self) -> frozenset[str]:
        return frozenset(
            severity
            for severity in _SEVERITY_ORDER
            if self.severity_buttons[severity].isChecked()
        )

    def _selected_source_row(self) -> int | None:
        return self.conflict_model.source_row(self.table.currentIndex())

    def _apply_filters(self, filters: FindingFilters) -> None:
        self.browser.set_filters(
            filters, selected_source_row=self._selected_source_row()
        )
        self._update_mod_filter_label(filters.package_id)
        self._restore_mod_selection()
        self._update_findings_feedback()

    def _clear_filter_inputs(self) -> None:
        self._clear_filter_widgets()
        self.mod_model.set_query("")

    def _clear_filter_widgets(self) -> None:
        blockers = [
            QSignalBlocker(self.mod_search),
            QSignalBlocker(self.finding_search),
            QSignalBlocker(self.type_filter),
        ]
        self.mod_search.clear()
        self.finding_search.clear()
        self.type_filter.setCurrentIndex(0)
        del blockers

    def _sync_filter_controls(self, filters: FindingFilters) -> None:
        blockers = [
            QSignalBlocker(self.finding_search),
            QSignalBlocker(self.type_filter),
        ]
        if self.finding_search.text() != filters.query:
            self.finding_search.setText(filters.query)
        self.type_filter.setCurrentIndex(self._type_index(filters.finding_type))
        del blockers
        self._set_severity_selection(filters.severities)
        self._update_mod_filter_label(filters.package_id)

    def _type_index(self, finding_type: str | None) -> int:
        for index in range(self.type_filter.count()):
            if self.type_filter.itemData(index) == finding_type:
                return index
        return 0

    def _mod_row_for_package(self, package_id: str) -> int | None:
        for row in range(1, self.mod_model.rowCount()):
            mod = self.mod_model.mod(self.mod_model.index(row, 0))
            if mod is not None and mod.package_id == package_id:
                return row
        return None

    def _restore_mod_selection(self) -> None:
        selection_model = self.mod_table.selectionModel()
        if selection_model is None:
            return
        blocker = QSignalBlocker(selection_model)
        package_id = self.browser.filters.package_id
        if package_id is None:
            index = self.mod_model.index(0, 0)
            self.mod_table.setCurrentIndex(index)
            self.mod_table.selectRow(0)
            del blocker
            return
        row = self._mod_row_for_package(package_id)
        if row is None:
            self.mod_table.clearSelection()
            self.mod_table.setCurrentIndex(_INVALID_INDEX)
            del blocker
            return
        index = self.mod_model.index(row, 0)
        self.mod_table.setCurrentIndex(index)
        self.mod_table.selectRow(row)
        del blocker

    def _update_mod_filter_label(self, package_id: str | None) -> None:
        if package_id is None:
            self.mod_filter_label.clear()
            self.mod_filter_label.setVisible(False)
            self._clear_mod_filter_button.setVisible(False)
            return
        label = package_id
        for mod in self.browser.mods:
            if mod.package_id != package_id:
                continue
            if mod.name != mod.package_id:
                label = self.tr("Mod filter: {name} ({package_id})").format(
                    name=mod.name,
                    package_id=mod.package_id,
                )
            else:
                label = self.tr("Mod filter: {package_id}").format(
                    package_id=mod.package_id
                )
            break
        self.mod_filter_label.setText(label)
        self.mod_filter_label.setVisible(True)
        self._clear_mod_filter_button.setVisible(True)

    @Slot()
    def _select_all_severities(self) -> None:
        self._set_severity_selection(_ALL_SEVERITIES)
        self._request_filters(_ALL_SEVERITIES)

    @Slot()
    def _apply_severity_filters(self) -> None:
        severities = self._current_severities()
        blocker = QSignalBlocker(self.severity_buttons["all"])
        self.severity_buttons["all"].setChecked(severities == _ALL_SEVERITIES)
        del blocker
        self._request_filters(severities)

    @Slot(str)
    def _apply_search_filters(self, _text: str) -> None:
        self._request_filters(self._current_severities())

    @Slot(int)
    def _apply_type_filter(self, _index: int) -> None:
        self._request_filters(self._current_severities())

    @Slot(str)
    def _apply_mod_search(self, text: str) -> None:
        self.mod_model.set_query(text)
        self._restore_mod_selection()
        if not text and self.browser.filters.package_id is None:
            self._restore_mod_selection()

    def _request_filters(self, severities: frozenset[str]) -> None:
        self._apply_filters(
            FindingFilters(
                severities=severities,
                package_id=self.browser.filters.package_id,
                query=self.finding_search.text(),
                finding_type=self.type_filter.currentData(),
            )
        )

    def set_mod_filter(self, package_id: str | None) -> None:
        if package_id is not None and all(
            mod.package_id != package_id for mod in self.browser.mods
        ):
            return
        self._apply_filters(
            FindingFilters(
                severities=self._current_severities(),
                package_id=package_id,
                query=self.finding_search.text(),
                finding_type=self.type_filter.currentData(),
            )
        )

    @Slot()
    def _reset_filters(self) -> None:
        self._clear_filter_widgets()
        self.browser.reset_filters(selected_source_row=self._selected_source_row())
        if self._teardown_complete:
            return
        self._sync_filter_controls(self.browser.filters)
        self.mod_model.set_query(self.mod_search.text())
        if self._teardown_complete:
            return
        self._sync_filter_controls(self.browser.filters)
        self._restore_mod_selection()
        self._update_findings_feedback()

    @Slot(QModelIndex, QModelIndex)
    def _mod_selection_changed(
        self, current: QModelIndex, _previous: QModelIndex
    ) -> None:
        if not current.isValid():
            return
        mod = self.mod_model.mod(current)
        self.set_mod_filter(None if mod is None else mod.package_id)

    @Slot()
    def _browser_prepared(self) -> None:
        conflicts = self.browser.conflicts
        mods = self.browser.mods
        self.mod_model.set_mods(mods)
        if self._teardown_complete or self.browser.conflicts is not conflicts:
            return
        if self.browser.mods is not mods:
            return
        self._sync_filter_controls(self.browser.filters)
        self._restore_mod_selection()

    @Slot(bool)
    def _browser_busy_changed(self, _busy: bool) -> None:
        if self._teardown_complete:
            return
        self._sync_filter_controls(self.browser.filters)
        self.inspector.set_mod_actions_enabled(not self.browser.busy)
        self._set_table_selection_enabled(not self.browser.busy)
        if not self.browser.busy:
            self._restore_pending_selection()
        self._update_findings_feedback()

    def _set_table_selection_enabled(self, enabled: bool) -> None:
        self.table.setSelectionMode(
            QTableView.SelectionMode.SingleSelection
            if enabled
            else QTableView.SelectionMode.NoSelection
        )
        self.table.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus if enabled else Qt.FocusPolicy.NoFocus
        )

    @Slot(object)
    def _apply_view(self, view: FindingView) -> None:
        self._sync_filter_controls(self.browser.filters)
        self.conflict_model.set_rows(self.browser.conflicts, view.source_rows)
        self._pending_selected_visible_row = view.selected_visible_row
        self._update_findings_feedback()

    def _restore_pending_selection(self) -> None:
        selected_visible_row = self._pending_selected_visible_row
        self._pending_selected_visible_row = None
        if selected_visible_row is None:
            self.table.clearSelection()
            self.table.setCurrentIndex(_INVALID_INDEX)
            self.inspector.set_finding(None)
            return
        index = self.conflict_model.index(selected_visible_row, 0)
        if not index.isValid():
            self.inspector.set_finding(None)
            return
        self.table.setCurrentIndex(index)
        self.table.selectRow(selected_visible_row)
        self._select_finding(index, _INVALID_INDEX)

    def _update_findings_feedback(self) -> None:
        if self.state != "finished":
            self.result_label.clear()
            self.result_label.setVisible(False)
            self.empty_label.clear()
            self.empty_label.setVisible(False)
            return
        self.result_label.setVisible(True)
        shown = self.conflict_model.rowCount()
        total = len(self.report.get("conflicts", []))
        self.result_label.setText(
            self.tr("Showing {shown} of {total} findings.").format(
                shown=self._format_count(shown),
                total=self._format_count(total),
            )
        )

        message = ""
        if self.browser.busy and self.conflict_model.rowCount() == 0:
            message = self.tr("Preparing findings…")
        elif self.browser.busy:
            message = self.tr("Updating findings…")
        elif not self.browser.filters.severities:
            message = self.tr("Choose at least one severity.")
        elif not self.report.get("conflicts"):
            message = self.tr("No findings reported.")
        elif self.conflict_model.rowCount() == 0:
            message = self.tr("No findings match the current filters.")
        self.empty_label.setText(message)
        self.empty_label.setVisible(bool(message))

    @Slot(QModelIndex, QModelIndex)
    def _select_finding(self, current: QModelIndex, _previous: QModelIndex) -> None:
        self.inspector.set_finding(self.conflict_model.finding(current))

    def show_report(self, report: dict[str, Any]) -> None:
        self.report = report
        self.state = "finished"
        self.is_incomplete = (
            bool(self.snapshot.issues) or self.snapshot.game_version is None
        )
        self._clear_filter_inputs()
        self.mod_model.set_mods(())
        self._update_mod_filter_label(None)
        self.inspector.set_finding(None)
        self.inspector.set_mod_actions_enabled(False)
        self._update_summary(report)
        self._show_diagnostics(report["diagnostics"])
        self.browser.set_report(report)
        self._set_severity_selection(self.browser.filters.severities)
        self._restore_mod_selection()
        self._update_findings_feedback()
        self._update_status()

    def _progress(
        self, request_id: str, _current: object, _total: object, _phase: str
    ) -> None:
        if request_id == self.request_id and self.state == "running":
            self._check_snapshot()

    def _succeeded(self, request_id: str, report: object) -> None:
        if (
            request_id == self.request_id
            and self.state == "running"
            and isinstance(report, dict)
        ):
            self._check_snapshot()
            self.show_report(report)

    def _failed(self, request_id: str, error: str) -> None:
        if request_id == self.request_id and self.state == "running":
            self.state = "failed"
            self._show_diagnostics([], error)
            self._update_findings_feedback()
            self._update_status()

    def _cancelled(self, request_id: str) -> None:
        if request_id == self.request_id and self.state in ("running", "cancelled"):
            self.state = "cancelled"
            self._update_findings_feedback()
            self._update_status()

    def cancel_scan(self) -> None:
        if self.state == "running":
            self.state = "cancelled"
            self.runner.cancel()
            self._update_findings_feedback()
            self._update_status()

    def _teardown_dialog(self) -> None:
        if self._teardown_complete:
            return
        self._teardown_complete = True
        self.browser.dispose()
        self.notes.dispose()
        self.cancel_scan()

    def done(self, result: int) -> None:
        self._teardown_dialog()
        super().done(result)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._teardown_dialog()
        super().closeEvent(event)
