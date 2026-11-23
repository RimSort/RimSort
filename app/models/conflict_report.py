"""Conflict report browsing models."""

import html
import textwrap
import time
from array import array
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import QApplication, QStyle

from app.services.conflict_snapshot import InputIssue, ScanSnapshot

_INVALID_INDEX = QModelIndex()
_ALL_SEVERITIES = frozenset({"error", "warning", "info"})
_SEVERITY_ORDER = ("error", "warning", "info")
_PREPARE_BUDGET_SECONDS = 0.008
_QUERY_DEBOUNCE_MILLISECONDS = 150
_WRAP_WIDTH = 72


@dataclass(frozen=True)
class FindingFilters:
    severities: frozenset[str]
    package_id: str | None = None
    query: str = ""
    finding_type: str | None = None


@dataclass(frozen=True)
class ModFindingCounts:
    package_id: str
    name: str
    error: int
    warning: int
    info: int


@dataclass(frozen=True)
class FindingView:
    generation: int
    source_rows: Sequence[int]
    selected_visible_row: int | None


@dataclass
class _MutableModFindingCounts:
    package_id: str
    name: str
    error: int = 0
    warning: int = 0
    info: int = 0

    def bump(self, severity: str) -> None:
        if severity == "error":
            self.error += 1
        elif severity == "warning":
            self.warning += 1
        elif severity == "info":
            self.info += 1


@dataclass(frozen=True)
class _DisplayedMod:
    package_id: str
    name: str


def safe_text(text: str) -> str:
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


@dataclass(frozen=True)
class NoteRef:
    kind: str
    index: int


_NOTE_SOURCES = (
    "xml_parsing",
    "dll_parsing",
    "metadata_resolution",
    "folder_resolution",
    "mods_config",
)


def _note_source_text(source: str) -> str:
    translate = QCoreApplication.translate
    return {
        "input": translate("ScanNotesModel", "Input"),
        "version": translate("ScanNotesModel", "Game version"),
        "failure": translate("ScanNotesModel", "Scan failure"),
        "xml_parsing": translate("ConflictReportDialog", "XML parsing"),
        "dll_parsing": translate("ConflictReportDialog", "DLL parsing"),
        "metadata_resolution": translate("ConflictReportDialog", "Metadata resolution"),
        "folder_resolution": translate("ConflictReportDialog", "Folder resolution"),
        "mods_config": translate("ConflictReportDialog", "Mod configuration"),
    }[source]


@dataclass
class _NoteDataset:
    snapshot: ScanSnapshot
    diagnostics: list[dict[str, Any]]
    error: str
    all_rows: dict[str, array[int]]
    attention_rows: dict[str, array[int]]
    attention_count: int
    incomplete: bool


class ScanNotesModel(QAbstractTableModel):
    prepared = Signal()
    busy_changed = Signal(bool)

    def __init__(
        self,
        format_diagnostic: Callable[[dict[str, Any]], str],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._format_diagnostic = format_diagnostic
        self._published: _NoteDataset | None = None
        self._building: _NoteDataset | None = None
        self._index = 0
        self._generation = 0
        self._disposed = False
        self._resetting = False
        self._show_info = False
        self._visible_show_info = False
        self.busy = False
        self.attention_count: int | None = 0
        self.incomplete = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._continue_preparation)
        self._view_timer = QTimer(self)
        self._view_timer.setSingleShot(True)
        self._view_timer.timeout.connect(self._apply_show_info)

    def set_notes(
        self, snapshot: ScanSnapshot, diagnostics: list[dict[str, Any]], error: str = ""
    ) -> None:
        if self._disposed:
            return
        self._generation += 1
        self._timer.stop()
        self._view_timer.stop()
        self._index = 0
        self._building = _NoteDataset(
            snapshot,
            diagnostics,
            error,
            {source: array("Q") for source in _NOTE_SOURCES},
            {source: array("Q") for source in _NOTE_SOURCES},
            len(snapshot.issues)
            + int(snapshot.game_version is None)
            + int(bool(error)),
            bool(snapshot.issues) or snapshot.game_version is None,
        )
        self.attention_count = None
        self._timer.start(0)
        self._set_busy(True)

    def set_show_info(self, show: bool) -> None:
        if self._disposed:
            return
        self._show_info = show
        if self.busy or self._resetting:
            if self._resetting and not self.busy:
                self._view_timer.start(0)
            return
        self._apply_show_info()

    def _apply_show_info(self) -> None:
        if self._disposed or self.busy or self._visible_show_info == self._show_info:
            return
        if self._resetting:
            self._view_timer.start(0)
            return
        generation = self._generation
        self._resetting = True
        self.beginResetModel()
        if not self._disposed and generation == self._generation:
            self._visible_show_info = self._show_info
        self.endResetModel()
        self._resetting = False
        if (
            not self._disposed
            and not self.busy
            and self._visible_show_info != self._show_info
        ):
            self._view_timer.start(0)

    def _continue_preparation(self) -> None:
        dataset = self._building
        if self._disposed or dataset is None:
            return
        generation = self._generation
        deadline = time.monotonic() + _PREPARE_BUDGET_SECONDS
        while self._index < len(dataset.diagnostics):
            diagnostic = dataset.diagnostics[self._index]
            source = diagnostic["source"]
            dataset.incomplete = dataset.incomplete or diagnostic["analysis_incomplete"]
            dataset.all_rows[source].append(self._index)
            if diagnostic["severity"] != "info" or diagnostic["analysis_incomplete"]:
                dataset.attention_rows[source].append(self._index)
                dataset.attention_count += 1
            self._index += 1
            if time.monotonic() >= deadline:
                if not self._disposed and generation == self._generation:
                    self._timer.start(1)
                return
        if self._resetting:
            self._timer.start(1)
            return
        self._resetting = True
        self.beginResetModel()
        if not self._disposed and generation == self._generation:
            self._published = dataset
            self._building = None
            self._visible_show_info = self._show_info
            self.attention_count = dataset.attention_count
            self.incomplete = dataset.incomplete
        self.endResetModel()
        self._resetting = False
        if self._disposed or generation != self._generation:
            return
        if self._visible_show_info != self._show_info:
            self._view_timer.start(0)
        self.prepared.emit()
        if self._disposed or generation != self._generation:
            return
        self._set_busy(False)
        if not self._disposed and generation == self._generation and not self.busy:
            self._apply_show_info()

    def _set_busy(self, busy: bool) -> None:
        if self.busy != busy:
            self.busy = busy
            self.busy_changed.emit(busy)

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._generation += 1
        self._timer.stop()
        self._view_timer.stop()
        self._building = None
        self._set_busy(False)

    def note(self, index: QModelIndex) -> NoteRef | None:
        dataset = self._published
        if dataset is None or not index.isValid() or index.row() < 0:
            return None
        row = index.row()
        issue_count = len(dataset.snapshot.issues)
        if row < issue_count:
            return NoteRef("input", row)
        row -= issue_count
        if dataset.snapshot.game_version is None:
            if row == 0:
                return NoteRef("version", 0)
            row -= 1
        groups = dataset.all_rows if self._visible_show_info else dataset.attention_rows
        for source in _NOTE_SOURCES:
            group = groups[source]
            if row < len(group):
                return NoteRef("native", int(group[row]))
            row -= len(group)
        if dataset.error and row == 0:
            return NoteRef("failure", 0)
        return None

    def _record(self, ref: NoteRef) -> InputIssue | dict[str, Any] | str | None:
        dataset = self._published
        if dataset is None:
            return None
        if ref.kind == "input":
            return dataset.snapshot.issues[ref.index]
        if ref.kind == "native":
            return dataset.diagnostics[ref.index]
        if ref.kind == "failure":
            return dataset.error
        if ref.kind == "version":
            return QCoreApplication.translate(
                "ConflictReportDialog",
                "Unknown game version: version-specific content may have been skipped.",
            )
        return None

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX
    ) -> int:
        dataset = self._published
        if parent.isValid() or dataset is None:
            return 0
        if not self._visible_show_info:
            return dataset.attention_count
        return (
            len(dataset.snapshot.issues)
            + int(dataset.snapshot.game_version is None)
            + len(dataset.diagnostics)
            + int(bool(dataset.error))
        )

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX
    ) -> int:
        return 0 if parent.isValid() else 2

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        return _header_label(
            (self.tr("Source"), self.tr("Message")), section, orientation, role
        )

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        ref = self.note(self.index(index.row(), index.column()))
        if ref is None:
            return None
        record = self._record(ref)
        if isinstance(record, dict):
            text = (
                _note_source_text(record["source"])
                if index.column() == 0
                else self._format_diagnostic(record)
            )
        elif isinstance(record, InputIssue):
            text = (
                _note_source_text(ref.kind) if index.column() == 0 else record.message
            )
        else:
            text = _note_source_text(ref.kind) if index.column() == 0 else str(record)
        return safe_text(text)


class ConflictReportBrowser(QObject):
    prepared = Signal()
    applied = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        all_filters = FindingFilters(_ALL_SEVERITIES)
        self.busy = False
        self.filters = all_filters
        self.initial_filters = all_filters
        self.conflicts: list[dict[str, Any]] = []
        self.mods: Sequence[ModFindingCounts] = ()

        self._disposed = False
        self._generation = 0
        self._prepared_generation = -1
        self._filter_request_generation = 0
        self._active_filter_request_generation = 0
        self._explicit_request_during_preparation = False
        self._reset_request_generation: int | None = None
        self._prepare_index = 0
        self._prepare_buckets: dict[str, array[int]] = {
            severity: array("Q") for severity in _SEVERITY_ORDER
        }
        self._prepare_mod_counts: dict[str, _MutableModFindingCounts] = {}
        self._requested_filters = all_filters
        self._requested_selected_source_row: int | None = None
        self._requested_filter_delay_ms = 0
        self._active_filters = all_filters
        self._active_selected_source_row: int | None = None
        self._active_filter_rows: array[int] = array("Q")
        self._active_filter_bucket_names: list[str] = []
        self._active_filter_bucket_index = 0
        self._active_filter_row_index = 0
        self._active_filter_selected_visible_row: int | None = None

        self._prepare_timer = QTimer(self)
        self._prepare_timer.setSingleShot(True)
        self._prepare_timer.timeout.connect(self._continue_preparation)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._continue_filtering)

    def set_report(self, report: dict[str, Any]) -> None:
        if self._disposed:
            return
        all_filters = FindingFilters(_ALL_SEVERITIES)
        self._generation += 1
        self._prepared_generation = -1
        self._filter_request_generation += 1
        self._active_filter_request_generation = 0
        self._explicit_request_during_preparation = False
        self._reset_request_generation = None
        self._prepare_timer.stop()
        self._filter_timer.stop()
        self.conflicts = report.get("conflicts", [])
        self.mods = ()
        self.initial_filters = all_filters
        self.filters = all_filters
        self._requested_filters = all_filters
        self._requested_selected_source_row = None
        self._requested_filter_delay_ms = 0
        self._active_filters = all_filters
        self._active_selected_source_row = None
        self._prepare_index = 0
        self._prepare_buckets = {severity: array("Q") for severity in _SEVERITY_ORDER}
        self._prepare_mod_counts = {}
        self._active_filter_rows = array("Q")
        self._active_filter_bucket_names = []
        self._active_filter_bucket_index = 0
        self._active_filter_row_index = 0
        self._active_filter_selected_visible_row = None
        self._prepare_timer.start(0)
        self._set_busy(True)

    def set_filters(
        self, filters: FindingFilters, selected_source_row: int | None = None
    ) -> None:
        if self._disposed:
            return
        self._reset_request_generation = None
        delay_ms = _query_debounce_delay(filters, self.filters)
        self._queue_filter_request(filters, selected_source_row, delay_ms)
        if self._prepared_generation != self._generation:
            self._explicit_request_during_preparation = True
            self._set_busy(True)
            return
        self._start_requested_filtering()

    def reset_filters(self, selected_source_row: int | None = None) -> None:
        """Clear non-severity constraints and restore the report default."""
        if self._disposed:
            return
        if self._prepared_generation != self._generation:
            self._queue_filter_request(
                FindingFilters(self.filters.severities),
                selected_source_row,
                0,
            )
            self._reset_request_generation = self._filter_request_generation
            self._explicit_request_during_preparation = False
            self._set_busy(True)
            return
        self._reset_request_generation = None
        self._queue_filter_request(
            FindingFilters(self.initial_filters.severities),
            selected_source_row,
            0,
        )
        self._start_requested_filtering()

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._generation += 1
        self._prepared_generation = -1
        self._filter_request_generation += 1
        self._reset_request_generation = None
        self._prepare_timer.stop()
        self._filter_timer.stop()
        self._set_busy(False)

    def _continue_preparation(self) -> None:
        if self._disposed:
            return
        generation = self._generation
        deadline = time.monotonic() + _PREPARE_BUDGET_SECONDS
        conflicts = self.conflicts
        while self._prepare_index < len(conflicts):
            finding = conflicts[self._prepare_index]
            severity = finding.get("severity")
            if severity in self._prepare_buckets:
                self._prepare_buckets[severity].append(self._prepare_index)
                for package_id, mod in _finding_participants(finding).items():
                    self._record_mod_count(package_id, mod, severity)
            self._prepare_index += 1
            if time.monotonic() >= deadline:
                if generation == self._generation and not self._disposed:
                    self._prepare_timer.start(1)
                return
        if generation != self._generation or self._disposed:
            return
        self.mods = _sorted_mod_counts(tuple(self._prepare_mod_counts.values()))
        self._prepared_generation = generation
        self.initial_filters = _default_filters_from_buckets(self._prepare_buckets)
        request_generation_before_prepared = self._filter_request_generation
        if self._reset_request_generation == request_generation_before_prepared:
            resolved_filters = FindingFilters(self.initial_filters.severities)
            self.filters = resolved_filters
            self._requested_filters = resolved_filters
            self._requested_filter_delay_ms = 0
            self._explicit_request_during_preparation = False
        self.prepared.emit()
        if (
            generation != self._generation
            or self._disposed
            or self._prepared_generation != generation
        ):
            return
        if self._filter_request_generation != request_generation_before_prepared:
            return
        if self._reset_request_generation == request_generation_before_prepared:
            self._reset_request_generation = None
            self._start_requested_filtering()
            return
        if self._explicit_request_during_preparation:
            self._start_requested_filtering()
            return
        self._queue_filter_request(self.initial_filters, None, 0)
        self._start_requested_filtering()

    def _record_mod_count(
        self, package_id: str, mod: _DisplayedMod, severity: str
    ) -> None:
        counts = self._prepare_mod_counts.get(package_id)
        if counts is None:
            counts = _MutableModFindingCounts(package_id=package_id, name=mod.name)
            self._prepare_mod_counts[package_id] = counts
        elif counts.name == counts.package_id and mod.name != mod.package_id:
            counts.name = mod.name
        counts.bump(severity)

    def _queue_filter_request(
        self,
        filters: FindingFilters,
        selected_source_row: int | None,
        delay_ms: int,
    ) -> None:
        self._filter_request_generation += 1
        self.filters = filters
        self._requested_filters = filters
        self._requested_selected_source_row = selected_source_row
        self._requested_filter_delay_ms = delay_ms

    def _start_requested_filtering(self) -> None:
        if self._disposed or self._prepared_generation != self._generation:
            return
        self._filter_timer.stop()
        self._active_filter_request_generation = self._filter_request_generation
        self._active_filters = self._requested_filters
        self._active_selected_source_row = self._requested_selected_source_row
        self._active_filter_rows = array("Q")
        self._active_filter_bucket_names = [
            severity
            for severity in _SEVERITY_ORDER
            if severity in self._active_filters.severities
        ]
        self._active_filter_bucket_index = 0
        self._active_filter_row_index = 0
        self._active_filter_selected_visible_row = None
        self._filter_timer.start(self._requested_filter_delay_ms)
        self._set_busy(True)

    def _continue_filtering(self) -> None:
        generation = self._generation
        request_generation = self._active_filter_request_generation
        if (
            self._disposed
            or self._prepared_generation != generation
            or request_generation != self._filter_request_generation
        ):
            return
        filters = self._active_filters
        selected_source_row = self._active_selected_source_row
        deadline = time.monotonic() + _PREPARE_BUDGET_SECONDS
        while self._active_filter_bucket_index < len(self._active_filter_bucket_names):
            bucket_name = self._active_filter_bucket_names[
                self._active_filter_bucket_index
            ]
            bucket = self._prepare_buckets[bucket_name]
            while self._active_filter_row_index < len(bucket):
                source_row = bucket[self._active_filter_row_index]
                self._active_filter_row_index += 1
                finding = self.conflicts[source_row]
                if _matches_filters(finding, filters):
                    self._active_filter_rows.append(source_row)
                    if (
                        selected_source_row is not None
                        and source_row == selected_source_row
                        and self._active_filter_selected_visible_row is None
                    ):
                        self._active_filter_selected_visible_row = (
                            len(self._active_filter_rows) - 1
                        )
                if time.monotonic() >= deadline:
                    if (
                        not self._disposed
                        and self._prepared_generation == generation
                        and request_generation == self._active_filter_request_generation
                        and request_generation == self._filter_request_generation
                    ):
                        self._filter_timer.start(1)
                    return
            self._active_filter_bucket_index += 1
            self._active_filter_row_index = 0
        if (
            self._disposed
            or self._prepared_generation != generation
            or request_generation != self._active_filter_request_generation
            or request_generation != self._filter_request_generation
        ):
            return
        selected_visible_row = self._active_filter_selected_visible_row
        source_rows: Sequence[int] = self._active_filter_rows
        if selected_visible_row is None and source_rows:
            selected_visible_row = 0
        self.applied.emit(
            FindingView(
                generation=generation,
                source_rows=source_rows,
                selected_visible_row=selected_visible_row,
            )
        )
        if (
            self._disposed
            or generation != self._generation
            or request_generation != self._active_filter_request_generation
            or request_generation != self._filter_request_generation
        ):
            return
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        if self.busy == busy:
            return
        self.busy = busy
        self.busy_changed.emit(busy)


class ConflictTableModel(QAbstractTableModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.conflicts: list[dict[str, Any]] = []
        self.source_rows: Sequence[int] = ()

    def set_rows(
        self, conflicts: list[dict[str, Any]], source_rows: Sequence[int]
    ) -> None:
        self.beginResetModel()
        self.conflicts = conflicts
        self.source_rows = source_rows
        self.endResetModel()

    def source_row(self, index: QModelIndex) -> int | None:
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self.source_rows):
            return None
        return int(self.source_rows[row])

    def finding(self, index: QModelIndex) -> dict[str, Any] | None:
        source_row = self.source_row(index)
        if source_row is None:
            return None
        return self.conflicts[source_row]

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX
    ) -> int:
        return 0 if parent.isValid() else len(self.source_rows)

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX
    ) -> int:
        return 0 if parent.isValid() else 3

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        return _header_label(
            (
                self.tr("Severity"),
                self.tr("Target / mechanism"),
                self.tr("Involved mods"),
            ),
            section,
            orientation,
            role,
        )

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self.source_rows):
            return None
        finding = self.conflicts[int(self.source_rows[row])]
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_text(finding, index.column())
        if role == Qt.ItemDataRole.ToolTipRole:
            text = self._display_text(finding, index.column())
            return _tooltip_html(text) if isinstance(text, str) and text else None
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return _severity_icon(finding["severity"])
        return None

    def _display_text(self, finding: dict[str, Any], column: int) -> str | None:
        if column == 0:
            return {
                "error": self.tr("Error"),
                "warning": self.tr("Warning"),
                "info": self.tr("Info"),
            }.get(finding["severity"])
        if column == 1:
            if finding["type"] == "def":
                target = finding["target"]
                target_text = safe_text(f"{target['def_type']}: {target['def_name']}")
                mechanism_text = self._def_mechanism_text(finding)
                return safe_text(f"{target_text} — {mechanism_text}")
            target = finding["target"]
            harmony = self.tr("Harmony")
            return safe_text(
                f"{target['type_name']}.{target['method_name']} — {harmony}"
            )
        if column == 2:
            return _mods_text(finding)
        return None

    def _def_mechanism_text(self, finding: dict[str, Any]) -> str:
        kind = next(iter(finding["mechanism"]))
        return {
            "direct_replacement": self.tr("Direct replacement"),
            "x_path_overlap": self.tr("XPath overlap"),
            "x_path_on_replaced_def": self.tr("XPath on replaced Def"),
            "xpath_same_def_non_overlap": self.tr("Non-overlapping XPath edits"),
        }[kind]


class ConflictModModel(QAbstractTableModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mods: Sequence[ModFindingCounts] = ()
        self._query = ""
        self._visible_rows: tuple[int, ...] = ()

    def set_mods(self, mods: Sequence[ModFindingCounts]) -> None:
        self.beginResetModel()
        self._mods = tuple(mods)
        self._visible_rows = self._matching_mod_rows(self._query)
        self.endResetModel()

    def set_query(self, query: str) -> None:
        self.beginResetModel()
        self._query = query
        self._visible_rows = self._matching_mod_rows(query)
        self.endResetModel()

    def mod(self, index: QModelIndex) -> ModFindingCounts | None:
        if not index.isValid() or index.row() <= 0:
            return None
        visible_row = index.row() - 1
        if visible_row < 0 or visible_row >= len(self._visible_rows):
            return None
        return self._mods[self._visible_rows[visible_row]]

    def rowCount(
        self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX
    ) -> int:
        return 0 if parent.isValid() else len(self._visible_rows) + 1

    def columnCount(
        self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX
    ) -> int:
        return 0 if parent.isValid() else 4

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        return _header_label(
            (
                self.tr("Mod"),
                self.tr("Errors"),
                self.tr("Warnings"),
                self.tr("Info"),
            ),
            section,
            orientation,
            role,
        )

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid():
            return None
        if role not in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.ToolTipRole,
        ):
            return None
        text = self._display_text(index)
        if role == Qt.ItemDataRole.DisplayRole:
            return text
        tooltip = self._tooltip_text(index)
        return _tooltip_html(tooltip) if tooltip else None

    def _display_text(self, index: QModelIndex | QPersistentModelIndex) -> str | None:
        if index.row() == 0:
            return self.tr("All mods") if index.column() == 0 else None
        mod = self.mod(self.index(index.row(), 0))
        if mod is None:
            return None
        if index.column() == 0:
            return safe_text(mod.name)
        if index.column() == 1:
            return _format_count(mod.error)
        if index.column() == 2:
            return _format_count(mod.warning)
        if index.column() == 3:
            return _format_count(mod.info)
        return None

    def _tooltip_text(self, index: QModelIndex | QPersistentModelIndex) -> str:
        if index.row() == 0:
            return self.tr("All mods")
        mod = self.mod(self.index(index.row(), 0))
        if mod is None:
            return ""
        if index.column() == 0 and mod.name != mod.package_id:
            return safe_text(f"{mod.name}\n{mod.package_id}")
        display = self._display_text(index)
        return display if isinstance(display, str) else ""

    def _matching_mod_rows(self, query: str) -> tuple[int, ...]:
        if not query:
            return tuple(range(len(self._mods)))
        match = query.casefold()
        visible_rows: list[int] = []
        for row, mod in enumerate(self._mods):
            if match in mod.name.casefold() or match in mod.package_id.casefold():
                visible_rows.append(row)
        return tuple(visible_rows)


def _header_label(
    headers: Sequence[str],
    section: int,
    orientation: Qt.Orientation,
    role: int,
) -> str | None:
    if orientation != Qt.Orientation.Horizontal or role != Qt.ItemDataRole.DisplayRole:
        return None
    return headers[section] if 0 <= section < len(headers) else None


def _default_filters_from_buckets(
    buckets: dict[str, array[int]],
) -> FindingFilters:
    for severity in _SEVERITY_ORDER:
        if len(buckets[severity]) > 0:
            return FindingFilters(frozenset({severity}))
    return FindingFilters(_ALL_SEVERITIES)


def _query_debounce_delay(filters: FindingFilters, previous: FindingFilters) -> int:
    if (
        filters.query != previous.query
        and filters.severities == previous.severities
        and filters.package_id == previous.package_id
        and filters.finding_type == previous.finding_type
    ):
        return _QUERY_DEBOUNCE_MILLISECONDS
    return 0


def _matches_filters(finding: dict[str, Any], filters: FindingFilters) -> bool:
    if filters.finding_type is not None and finding.get("type") != filters.finding_type:
        return False
    if filters.package_id is not None and filters.package_id not in _package_ids(
        finding
    ):
        return False
    if not filters.query:
        return True
    query = filters.query.casefold()
    return any(query in token.casefold() for token in _finding_tokens(finding))


def _package_ids(finding: dict[str, Any]) -> set[str]:
    return set(_finding_participants(finding))


def _finding_participants(finding: dict[str, Any]) -> dict[str, _DisplayedMod]:
    participants: dict[str, _DisplayedMod] = {}
    for displayed in _iter_finding_participants(finding):
        current = participants.get(displayed.package_id)
        if current is None or (
            current.name == current.package_id
            and displayed.name != displayed.package_id
        ):
            participants[displayed.package_id] = displayed
    return participants


def _iter_finding_participants(finding: dict[str, Any]) -> Iterator[_DisplayedMod]:
    if finding.get("type") == "def":
        raw_mods = finding.get("mods", [])
    else:
        raw_mods = [
            patch.get("mod_summary")
            for patch in finding.get("patches", [])
            if isinstance(patch, dict)
        ]
    for raw_mod in raw_mods:
        if not isinstance(raw_mod, dict):
            continue
        package_id = raw_mod.get("package_id")
        if not isinstance(package_id, str):
            continue
        yield _DisplayedMod(
            package_id=package_id,
            name=_display_mod_name(package_id, raw_mod.get("name")),
        )


def _display_mod_name(package_id: str, name: object) -> str:
    if isinstance(name, str) and name:
        return safe_text(name)
    return safe_text(package_id)


def _finding_tokens(finding: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    target = finding.get("target")
    if isinstance(target, dict):
        if finding.get("type") == "def":
            def_type = target.get("def_type")
            def_name = target.get("def_name")
            if isinstance(def_type, str):
                tokens.append(safe_text(def_type))
            if isinstance(def_name, str):
                tokens.append(safe_text(def_name))
            if isinstance(def_type, str) and isinstance(def_name, str):
                tokens.append(safe_text(f"{def_type}: {def_name}"))
        else:
            type_name = target.get("type_name")
            method_name = target.get("method_name")
            if isinstance(type_name, str):
                tokens.append(safe_text(type_name))
            if isinstance(method_name, str):
                tokens.append(safe_text(method_name))
            if isinstance(type_name, str) and isinstance(method_name, str):
                tokens.append(safe_text(f"{type_name}.{method_name}"))
    for mod in _iter_finding_participants(finding):
        tokens.append(mod.name)
        tokens.append(safe_text(mod.package_id))
    return tokens


def _sorted_mod_counts(
    counts: Sequence[_MutableModFindingCounts],
) -> tuple[ModFindingCounts, ...]:
    return tuple(
        ModFindingCounts(
            package_id=count.package_id,
            name=count.name,
            error=count.error,
            warning=count.warning,
            info=count.info,
        )
        for count in sorted(
            counts,
            key=lambda mod: (
                -mod.error,
                -mod.warning,
                -mod.info,
                mod.name.casefold(),
                mod.package_id.casefold(),
            ),
        )
    )


def _mods_text(finding: dict[str, Any]) -> str:
    if finding["type"] == "def":
        mods = finding.get("mods", [])
    else:
        mods = [patch["mod_summary"] for patch in finding.get("patches", [])]
    return safe_text(
        ", ".join(_display_mod_name(mod["package_id"], mod.get("name")) for mod in mods)
    )


def _format_count(count: int) -> str:
    from PySide6.QtCore import QLocale

    return QLocale().toString(count)


def _tooltip_html(text: str) -> str:
    wrapped = "\n".join(textwrap.wrap(text, width=_WRAP_WIDTH) or [text])
    escaped = html.escape(safe_text(wrapped)).replace("\n", "<br/>")
    return f"<qt><p style='white-space:pre-wrap'>{escaped}</p></qt>"


def _severity_icon(severity: str) -> object:
    style = QApplication.style()
    if style is None:
        return None
    icons = {
        "error": QStyle.StandardPixmap.SP_MessageBoxCritical,
        "warning": QStyle.StandardPixmap.SP_MessageBoxWarning,
        "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
    }
    standard_icon = icons.get(severity)
    return style.standardIcon(standard_icon) if standard_icon is not None else None
