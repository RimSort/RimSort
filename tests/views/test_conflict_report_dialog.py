"""Behavior of the conflict report dialog."""

import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
import shiboken6
from PySide6.QtCore import (
    QCoreApplication,
    QObject,
    QRect,
    Qt,
    QTimer,
    QTranslator,
    Signal,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QWidgetItem,
)

from app.controllers.metadata_controller import MetadataController
from app.models.conflict_report import FindingFilters
from app.models.metadata.metadata_structure import AboutXmlMod
from app.services.conflict_detector_runner import ConflictDetectorRunner
from app.services.conflict_snapshot import snapshot_active_mods
from app.utils.event_bus import EventBus
from app.views.conflict_report_details import FindingInspector
from app.windows.conflict_report_dialog import ConflictReportDialog, _diagnostic_message
from tests.conflict_detector_fixtures import (
    extract_context_sources,
    force_one_row_per_tick,
    make_large_triage_report,
    make_notes_diagnostics,
    make_report,
    make_triage_report,
    make_triage_report_with_counts,
    make_triage_report_with_moved_selection,
)
from tests.views.test_mods_panel import _make_active_mod_list, make_two_mod_list


class FakeMetadata(QObject):
    metadata_refresh_started = Signal()
    metadata_refreshed = Signal()
    mod_created_signal = Signal(str)
    mod_deleted_signal = Signal(str)
    mod_metadata_updated_signal = Signal(str)

    def __init__(self, source: Any) -> None:
        super().__init__()
        self.get_mod = source.get_mod
        self.game_version = source.game_version


class FakeRunner(ConflictDetectorRunner):
    def __init__(self) -> None:
        super().__init__()
        self.request: dict[str, Any] | None = None
        self.cancel_called = False
        self.cancel_calls = 0
        self.start_calls = 0

    def start(self, request: dict[str, Any]) -> None:
        self.start_calls += 1
        self.request = request

    def cancel(self) -> None:
        self.cancel_called = True
        self.cancel_calls += 1


@pytest.fixture
def dialog_setup(qtbot: Any, tmp_path: Path) -> tuple[Any, Any, FakeRunner]:
    widget, _, _ = make_two_mod_list(qtbot, tmp_path)
    metadata = FakeMetadata(widget.metadata_controller)
    widget.metadata_controller = cast(MetadataController, metadata)
    runner = FakeRunner()
    snapshot = snapshot_active_mods(widget, widget.metadata_controller, "instance-a")
    dialog = ConflictReportDialog(
        widget, widget.metadata_controller, lambda: "instance-a", snapshot, runner
    )
    qtbot.addWidget(dialog)
    return dialog, widget, runner


def _wait_for_view(qtbot: Any, dialog: ConflictReportDialog) -> None:
    qtbot.waitUntil(lambda: not dialog.browser.busy)


class NonIterableSourceRows:
    def __init__(self, rows: list[int]) -> None:
        self._rows = rows

    def __getitem__(self, index: int | slice) -> object:
        return self._rows[index]

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[int]:
        raise AssertionError("visible row mapping should not be iterated")


class FakeScreen:
    def __init__(self, rect: QRect) -> None:
        self._rect = rect

    def availableGeometry(self) -> QRect:
        return self._rect


def _conflicting_summary_report() -> dict[str, Any]:
    report = make_triage_report()
    report["summary"]["conflicts_by_severity"] = {
        "error": 0,
        "warning": 1,
        "info": 1,
    }
    return report


def _close_button(dialog: ConflictReportDialog) -> QPushButton:
    return next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.text() == dialog.tr("Close")
    )


def _process_next_event_turn(qtbot: Any) -> None:
    finished: list[bool] = []
    QTimer.singleShot(0, lambda: finished.append(True))
    qtbot.waitUntil(lambda: bool(finished))


def _assert_dialog_fits_screen(
    dialog: ConflictReportDialog, width: int, height: int
) -> None:
    minimum = dialog.minimumSizeHint()
    assert dialog.width() <= width
    assert dialog.height() <= height
    assert dialog.width() < 900
    assert dialog.height() < 650
    assert dialog.minimumWidth() <= width
    assert dialog.minimumHeight() <= height
    assert dialog.width() >= minimum.width()
    assert dialog.height() >= minimum.height()


def _show_report_and_wait(
    qtbot: Any, dialog: ConflictReportDialog, report: dict[str, Any]
) -> None:
    dialog.show_report(report)
    _wait_for_view(qtbot, dialog)


def _show_visible_triage_report(
    qtbot: Any, dialog: ConflictReportDialog
) -> dict[str, Any]:
    dialog.show()
    report = make_triage_report()
    _show_report_and_wait(qtbot, dialog, report)
    return report


type RawTriageDialog = tuple[ConflictReportDialog, dict[str, Any], FindingInspector]


@pytest.fixture
def raw_triage_dialog(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> RawTriageDialog:
    dialog, _, _ = dialog_setup
    report = _show_visible_triage_report(qtbot, dialog)
    inspector = dialog.inspector
    inspector.raw_button.click()
    assert (
        dialog.conflict_model.finding(dialog.table.currentIndex())
        is report["conflicts"][1]
    )
    assert inspector._finding is report["conflicts"][1]
    assert inspector.raw_button.isChecked()
    assert json.loads(inspector.raw_view.toPlainText()) == report["conflicts"][1]
    return dialog, report, inspector


def _select_note(
    qtbot: Any, dialog: ConflictReportDialog, kind: str, index: int = 0
) -> None:
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    for row in range(dialog.notes.model.rowCount()):
        ref = dialog.notes.model.note(dialog.notes.model.index(row, 0))
        if ref is not None and ref.kind == kind and ref.index == index:
            dialog.notes.table.selectRow(row)
            return
    raise AssertionError(f"note not found: {kind} {index}")


def _button_text(button: QPushButton) -> str:
    return button.text().replace("&&", "&")


def _inspector_text(dialog: ConflictReportDialog) -> str:
    texts = [
        label.text() for label in dialog.inspector.findChildren(QLabel) if label.text()
    ]
    texts.extend(
        _button_text(button)
        for button in dialog.inspector.findChildren(QPushButton)
        if _button_text(button)
    )
    raw = dialog.inspector.raw_view.toPlainText()
    if raw:
        texts.append(raw)
    return "\n".join(texts)


def _mod_action_buttons(dialog: ConflictReportDialog) -> list[QPushButton]:
    return list(dialog.inspector._participants_widget.findChildren(QPushButton))


def _install_translator(
    tmp_path: Path, name: str, catalog_text: str
) -> tuple[QCoreApplication, QTranslator]:
    lrelease = shutil.which("pyside6-lrelease")
    assert lrelease is not None
    catalog = tmp_path / f"{name}.ts"
    catalog.write_text(catalog_text, encoding="utf-8")
    qm = tmp_path / f"{name}.qm"
    subprocess.run([lrelease, str(catalog), "-qm", str(qm)], check=True)
    translator = QTranslator()
    assert translator.load(str(qm))
    app = QCoreApplication.instance()
    assert app is not None
    app.installTranslator(translator)
    return app, translator


def _select_mod_row(dialog: ConflictReportDialog, package_id: str) -> int:
    for row in range(dialog.mod_model.rowCount()):
        mod = dialog.mod_model.mod(dialog.mod_model.index(row, 0))
        if mod is not None and mod.package_id == package_id:
            dialog.mod_table.selectRow(row)
            return row
    raise AssertionError(f"package id not found in sidebar: {package_id}")


def _visible_sidebar_package_ids(dialog: ConflictReportDialog) -> list[str]:
    return [
        mod.package_id
        for row in range(1, dialog.mod_model.rowCount())
        if (mod := dialog.mod_model.mod(dialog.mod_model.index(row, 0))) is not None
    ]


def _filter_to_example_c_harmony_pawn(qtbot: Any, dialog: ConflictReportDialog) -> None:
    dialog.severity_buttons["all"].click()
    _wait_for_view(qtbot, dialog)
    _select_mod_row(dialog, "example.c")
    dialog.finding_search.setText("Pawn")
    dialog.type_filter.setCurrentIndex(2)
    _wait_for_view(qtbot, dialog)


def _assert_shared_query_rows(
    dialog: ConflictReportDialog,
    *,
    finding_type: str | None,
    mod_search_text: str | None = None,
) -> None:
    assert dialog.browser.filters.severities == frozenset({"error", "warning", "info"})
    assert dialog.browser.filters.package_id is None
    assert dialog.browser.filters.query == "Shared"
    assert dialog.browser.filters.finding_type == finding_type
    assert list(dialog.conflict_model.source_rows) == [1, 0]
    if mod_search_text is not None:
        assert dialog.mod_search.text() == mod_search_text


def _start_report_preparation(
    dialog: ConflictReportDialog,
    monkeypatch: pytest.MonkeyPatch,
    report: dict[str, Any],
) -> None:
    force_one_row_per_tick(monkeypatch)
    dialog.show_report(report)
    assert dialog.browser.busy


def _start_conflicting_report_preparation(
    dialog: ConflictReportDialog, monkeypatch: pytest.MonkeyPatch
) -> None:
    _start_report_preparation(dialog, monkeypatch, _conflicting_summary_report())


def _checked_severities(dialog: ConflictReportDialog) -> frozenset[str]:
    return frozenset(
        severity
        for severity in ("error", "warning", "info")
        if dialog.severity_buttons[severity].isChecked()
    )


def _observe_next_mod_model_reset(
    dialog: ConflictReportDialog, callback: Callable[[], None]
) -> list[bool]:
    hits: list[bool] = []

    def on_model_reset() -> None:
        if hits:
            return
        hits.append(True)
        callback()

    dialog.mod_model.modelReset.connect(on_model_reset)
    return hits


def _preparation_progress(dialog: ConflictReportDialog) -> tuple[int, int]:
    browser = dialog.browser
    return browser._prepare_index, len(browser.conflicts)


def _filter_progress(dialog: ConflictReportDialog) -> tuple[int, int]:
    browser = dialog.browser
    bucket_names = browser._active_filter_bucket_names
    traversed = (
        sum(
            len(browser._prepare_buckets[name])
            for name in bucket_names[: browser._active_filter_bucket_index]
        )
        + browser._active_filter_row_index
    )
    total = sum(len(browser._prepare_buckets[name]) for name in bucket_names)
    return traversed, total


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("load_after_violation", "'a' declares loadAfter 'b' but is loaded before it"),
        ("load_before_violation", "'a' declares loadBefore 'b' but is loaded after it"),
        (
            "force_load_after_violation",
            "'a' declares forceLoadAfter 'b' but is loaded before it (hard constraint violated)",
        ),
        (
            "force_load_before_violation",
            "'a' declares forceLoadBefore 'b' but is loaded after it (hard constraint violated)",
        ),
    ],
)
def test_load_order_diagnostic_templates(code: str, expected: str) -> None:
    assert (
        _diagnostic_message(
            {"code": code, "params": {"mod": "a", "dependency": "b"}, "message": "raw"}
        )
        == expected
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            "xml_abstract_defs_skipped",
            "Skipped 2 abstract def(s) without a usable defName",
        ),
        (
            "xml_unnamed_defs_skipped",
            "Skipped 2 def(s) without defName (unindexable; RimWorld auto-names these at runtime)",
        ),
    ],
)
def test_skipped_def_diagnostic_templates(code: str, expected: str) -> None:
    assert (
        _diagnostic_message({"code": code, "params": {"count": "2"}, "message": "raw"})
        == expected
    )


@pytest.mark.parametrize(
    ("code", "params", "expected"),
    [
        (
            "manual_dll_read_failure",
            {"path": "p", "detail": "bad"},
            "Failed to read DLL for manual patch detection p: bad",
        ),
        (
            "manual_dll_scan_panic",
            {"path": "p"},
            "Manual patch detection panicked while scanning p (caught; results for this DLL may be incomplete)",
        ),
        (
            "manual_patch_hint",
            {"dll": "x", "method": "m"},
            "Possible manual patch hint in x: m (best-effort heuristic, may be a false positive)",
        ),
        (
            "harmony_parse_failure",
            {"dll": "x", "detail": "bad"},
            "Failed to parse Harmony patches from x: bad",
        ),
        (
            "harmony_parse_panic",
            {"dll": "x"},
            "DLL parser panicked while parsing x (dotnetdll crash caught)",
        ),
        (
            "invalid_game_version",
            {"version": "bad", "version_debug": '"bad"'},
            'Invalid game version "bad"; falling back to default folder selection',
        ),
        (
            "unknown_config_fields",
            {"fields": "foo, bar"},
            "Unknown config fields ignored: foo, bar",
        ),
        ("mod_directory_missing", {"path": "p"}, "Mod directory does not exist: p"),
        (
            "mod_directory_not_directory",
            {"path": "p"},
            "Mod directory is not a directory: p",
        ),
        (
            "mods_config_parse_failure",
            {"path": "p", "detail": "bad"},
            "Failed to parse ModsConfig.xml: bad",
        ),
        (
            "active_mod_not_found",
            {"package_id": "a"},
            "Mod 'a' not found in search directories (a mod folder may have failed to parse — see \"Failed to parse mod at\" diagnostics in this report)",
        ),
        (
            "load_folders_parse_failure",
            {"path": "p", "detail": "bad"},
            "Failed to parse LoadFolders.xml; using implicit folder resolution: bad",
        ),
        (
            "load_folders_unknown_conditions",
            {"conditions": "foo"},
            "Unknown LoadFolders.xml condition attributes: foo",
        ),
        (
            "load_folders_inspection_failure",
            {"path": "p", "detail": "bad"},
            "Failed to inspect LoadFolders.xml in p; using implicit folder resolution: bad",
        ),
        (
            "content_directory_inspection_failure",
            {"path": "p", "detail": "bad"},
            "Failed to inspect content directory p: bad",
        ),
        ("load_folders_empty", {}, "LoadFolders.xml selected no folders"),
        (
            "load_folders_empty_invalid_paths",
            {"paths": '"../x", "/x"'},
            'LoadFolders.xml selected no folders; invalid paths skipped: "../x", "/x"',
        ),
        (
            "load_folders_invalid_paths",
            {"paths": '"../x"'},
            'Invalid LoadFolders.xml folder paths skipped: "../x"',
        ),
        (
            "load_folders_no_applicable_version",
            {},
            "No applicable LoadFolders.xml version entry; using implicit folder resolution",
        ),
        ("content_symlink_skipped", {"path": "p"}, "Skipped symlink p"),
        (
            "content_enumeration_failure",
            {"path": "p", "detail": "bad"},
            "Failed to enumerate p: bad",
        ),
    ],
)
def test_detector_diagnostic_templates(
    code: str, params: dict[str, str], expected: str
) -> None:
    assert (
        _diagnostic_message({"code": code, "params": params, "message": "raw"})
        == expected
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("mod_directory_read_failure", "Failed to read directory p: bad"),
        (
            "mod_directory_entry_read_failure",
            "Failed to read directory entry in p: bad",
        ),
    ],
)
def test_discovery_diagnostic_templates(code: str, expected: str) -> None:
    assert (
        _diagnostic_message(
            {"code": code, "params": {"path": "p", "detail": "bad"}, "message": "raw"}
        )
        == expected
    )


def test_content_not_directory_template() -> None:
    assert (
        _diagnostic_message(
            {
                "code": "content_path_not_directory",
                "params": {"path": "p", "detail": "not a directory"},
                "message": "raw",
            }
        )
        == "Failed to inspect content directory p: not a directory"
    )


def test_xml_read_diagnostic_template() -> None:
    assert (
        _diagnostic_message(
            {
                "code": "xml_read_failure",
                "params": {"path": "p", "detail": "bad"},
                "message": "raw",
            }
        )
        == "Failed to read p: bad"
    )


@pytest.mark.parametrize(
    ("code", "params", "expected"),
    [
        (
            "xml_parse_failure",
            {"path": "p", "detail": "bad"},
            "XML parse error in p: bad",
        ),
        (
            "xml_unclosed_elements",
            {"path": "p", "count": "2"},
            "XML parse error in p: document ends with 2 unclosed element(s) (results may be incomplete)",
        ),
        (
            "xml_def_name_decode_failure",
            {"path": "p", "detail": "bad"},
            "defName in p could not be decoded: bad",
        ),
        (
            "xml_def_name_unexpected_close",
            {"path": "p", "tag": "x"},
            "defName in p closed by unexpected </x>; def dropped",
        ),
        (
            "xml_def_name_unclosed",
            {"path": "p"},
            "defName in p is not closed; def dropped",
        ),
        (
            "xml_def_name_nested",
            {"path": "p"},
            "defName in p contains nested markup; defName is a leaf: def dropped",
        ),
        (
            "xml_patch_depth_exceeded",
            {"path": "p", "depth": "64"},
            "Patch operation nesting exceeds maximum depth 64 in p; skipping operation",
        ),
        (
            "xml_text_decode_failure",
            {"path": "p", "element": "xpath", "detail": "bad"},
            "Malformed <xpath> text in p: bad",
        ),
        (
            "xml_text_nested",
            {"path": "p", "element": "xpath"},
            "Nested element in <xpath> text in p",
        ),
        (
            "xml_text_mismatched",
            {"path": "p", "element": "li"},
            "Mismatched element in <li> text in p",
        ),
        (
            "xml_text_mismatched_end",
            {"path": "p", "element": "li"},
            "Mismatched end element in <li> text in p",
        ),
        (
            "xml_text_unexpected_eof",
            {"path": "p", "element": "li"},
            "Unexpected EOF in <li> text in p",
        ),
        (
            "xml_reconstruction_parse_failure",
            {"def_id": "ThingDef:Steel", "detail": "bad"},
            "internal XML reconstruction error for ThingDef:Steel: bad",
        ),
        (
            "xml_reconstruction_text_failure",
            {"def_id": "ThingDef:Steel", "detail": "bad"},
            "internal XML reconstruction error for ThingDef:Steel: text decode failed: bad",
        ),
        (
            "xml_reconstruction_attribute_failure",
            {"def_id": "ThingDef:Steel", "detail": "bad"},
            "internal XML reconstruction error for ThingDef:Steel: attribute decode failed: bad",
        ),
    ],
)
def test_xml_structural_diagnostic_templates(
    code: str, params: dict[str, str], expected: str
) -> None:
    diagnostic = {"code": code, "params": params, "message": "raw"}
    assert _diagnostic_message(diagnostic) == expected


@pytest.mark.parametrize("broken", ["{missing}", "{path", "{path.invalid}"])
def test_malformed_translated_diagnostic_template_falls_back(
    monkeypatch: pytest.MonkeyPatch, broken: str
) -> None:
    monkeypatch.setattr(QCoreApplication, "translate", lambda context, source: broken)
    assert (
        _diagnostic_message(
            {
                "code": "xml_parse_failure",
                "params": {"path": "p", "detail": "bad"},
                "message": "raw",
            }
        )
        == "raw"
    )


@pytest.mark.parametrize(
    ("translation", "params", "expected"),
    [
        ("Erreur XML", {"path": "p", "detail": "bad"}, "raw"),
        ("Erreur {path}", {"path": "p", "detail": "bad"}, "raw"),
        (
            "{path}: {detail} {extra}",
            {"path": "p", "detail": "bad", "extra": "x"},
            "raw",
        ),
        ("Erreur XML", {"path": "p"}, "raw"),
        ("{detail} dans {path}", {"path": "p"}, "raw"),
        ("{detail} dans {path}", {"path": "p", "detail": "bad"}, "bad dans p"),
        (
            "{{XML}} {detail} dans {path}",
            {"path": "p", "detail": "bad"},
            "{XML} bad dans p",
        ),
        ("{path.__class__} {detail}", {"path": "p", "detail": "bad"}, "raw"),
        ("{path:{detail}}", {"path": "p", "detail": "bad"}, "raw"),
    ],
)
def test_translated_diagnostic_placeholders(
    monkeypatch: pytest.MonkeyPatch,
    translation: str,
    params: dict[str, str],
    expected: str,
) -> None:
    monkeypatch.setattr(
        QCoreApplication, "translate", lambda context, source: translation
    )
    assert (
        _diagnostic_message(
            {"code": "xml_parse_failure", "params": params, "message": "raw"}
        )
        == expected
    )


@pytest.mark.parametrize("side", ["source", "translation"])
@pytest.mark.parametrize(
    "template",
    [
        "{path:{detail}}",
        "{path} {detail:.0}",
        "{path} {detail!r}",
        "{path} {detail!s}",
        "{path} {detail!a}",
        "{path[0]} {detail}",
        "{path} {detail:20}",
    ],
)
def test_diagnostic_rejects_non_bare_fields(
    monkeypatch: pytest.MonkeyPatch, side: str, template: str
) -> None:
    from app.windows import conflict_report_dialog

    if side == "source":
        monkeypatch.setattr(
            conflict_report_dialog,
            "QT_TRANSLATE_NOOP",
            lambda context, source: template,
        )
        monkeypatch.setattr(
            QCoreApplication, "translate", lambda context, source: source
        )
    else:
        monkeypatch.setattr(
            QCoreApplication, "translate", lambda context, source: template
        )
    assert (
        _diagnostic_message(
            {
                "code": "xml_parse_failure",
                "params": {"path": "file.xml", "detail": "20"},
                "message": "raw",
            }
        )
        == "raw"
    )


@pytest.mark.parametrize("severity", ["error", "warning", "info"])
def test_fixture_severity_summary(severity: str) -> None:
    report = make_report(severity, False)
    counts = report["summary"]["conflicts_by_severity"]
    assert counts == {
        name: int(name == severity) for name in ("error", "warning", "info")
    }


def test_selection_reset_disposes_outer_layout_items(qtbot: Any) -> None:
    inspector = FindingInspector()
    qtbot.addWidget(inspector)
    layout = inspector._content_layout
    old_widgets = (inspector._participants_widget, inspector._details_widget)
    positions = tuple(layout.indexOf(widget) for widget in old_widgets)
    assert all(position >= 0 for position in positions)
    tracked = []
    for position, widget in zip(positions, old_widgets, strict=True):
        layout.removeWidget(widget)
        item = QWidgetItem(widget)
        layout.insertItem(position, item)
        assert layout.itemAt(position) is item
        assert shiboken6.isValid(item)
        assert not shiboken6.ownedByPython(item)
        tracked.append(item)

    inspector.set_finding(None)

    assert [shiboken6.isValid(item) for item in tracked] == [False, False]
    assert all(shiboken6.isValid(widget) for widget in old_widgets)
    new_widgets = (inspector._participants_widget, inspector._details_widget)
    assert all(shiboken6.isValid(widget) for widget in new_widgets)
    assert tuple(layout.indexOf(widget) for widget in new_widgets) == positions
    qtbot.waitUntil(
        lambda: all(not shiboken6.isValid(widget) for widget in old_widgets)
    )
    assert all(shiboken6.isValid(widget) for widget in new_widgets)


def test_inspector_does_not_serialize_selected_finding_until_disclosed(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    serialized: list[object] = []
    original = json.dumps

    def spy(value: object, *args: Any, **kwargs: Any) -> str:
        serialized.append(value)
        return original(value, *args, **kwargs)

    monkeypatch.setattr(json, "dumps", spy)
    _show_report_and_wait(qtbot, dialog, report)
    assert (
        dialog.conflict_model.finding(dialog.table.currentIndex())
        is report["conflicts"][1]
    )
    assert not any(value is report["conflicts"][1] for value in serialized)

    dialog.inspector.technical_button.click()
    assert not any(value is report["conflicts"][1] for value in serialized)
    assert dialog.inspector.raw_view.toPlainText() == ""
    dialog.inspector.raw_button.click()

    assert any(value is report["conflicts"][1] for value in serialized)
    assert json.loads(dialog.inspector.raw_view.toPlainText()) == report["conflicts"][1]


def test_harmony_technical_fields_are_not_built_before_disclosure(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    _show_report_and_wait(qtbot, dialog, make_triage_report())
    dialog.table.selectRow(1)
    labels = [label.text() for label in dialog.inspector.findChildren(QLabel)]
    assert not any("a-main.dll" in text for text in labels)
    assert "example.c" in " ".join(
        _button_text(button)
        for button in _mod_action_buttons(dialog)
        if button.isEnabled()
    )
    assert "Def-style winner" in dialog.inspector.outcome_label.text()


def test_technical_disclosure_keyboard_independence_and_reset(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = _show_visible_triage_report(qtbot, dialog)
    inspector = dialog.inspector
    dialog.table.selectRow(1)
    assert inspector._details_layout.count() == 0
    inspector.raw_button.click()
    assert inspector._details_layout.count() == 0
    assert json.loads(inspector.raw_view.toPlainText()) == report["conflicts"][3]
    inspector.raw_button.click()
    inspector.technical_button.setFocus()
    qtbot.keyClick(inspector.technical_button, Qt.Key.Key_Space)
    assert inspector.technical_button.isChecked()
    assert inspector._details_widget.isVisible()
    text = " ".join(
        label.text() for label in inspector._details_widget.findChildren(QLabel)
    )
    for value in ("a-main.dll", "a-extra.dll", "c.dll", "400", "300", "200"):
        assert value in text
    assert inspector.raw_view.toPlainText() == ""
    qtbot.keyClick(inspector.technical_button, Qt.Key.Key_Space)
    assert not inspector._details_widget.isVisible()
    qtbot.keyClick(inspector.technical_button, Qt.Key.Key_Space)
    assert inspector._details_widget.isVisible()
    dialog.table.selectRow(0)
    assert not inspector.technical_button.isChecked()
    assert not inspector.raw_button.isChecked()
    assert inspector._details_layout.count() == 0


def test_inspector_is_structured_and_raw_is_lazy(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    _show_report_and_wait(qtbot, dialog, report)

    details = _inspector_text(dialog)
    assert (
        dialog.conflict_model.finding(dialog.table.currentIndex())
        is report["conflicts"][1]
    )
    assert dialog.tr("Severity") in details
    assert dialog.tr("Target") in details
    assert dialog.tr("Mechanism") in details
    assert dialog.tr("Reported outcome") in details
    assert dialog.tr("Direct replacement") in details
    assert "example.b" in dialog.inspector.outcome_label.text()
    assert dialog.inspector.raw_view.toPlainText() == ""

    dialog.inspector.raw_button.click()

    assert json.loads(dialog.inspector.raw_view.toPlainText()) == report["conflicts"][1]

    dialog.table.selectRow(1)

    assert (
        dialog.conflict_model.finding(dialog.table.currentIndex())
        is report["conflicts"][3]
    )
    assert dialog.inspector.raw_view.toPlainText() == ""
    assert not dialog.inspector.raw_button.isChecked()
    assert "example.b" not in dialog.inspector.outcome_label.text()
    assert (
        "Harmony patches do not report a Def-style winner."
        in dialog.inspector.outcome_label.text()
    )


def test_inspector_reselecting_same_finding_reference_clears_raw_disclosure(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    report["conflicts"].append(report["conflicts"][1])
    report["summary"]["conflicts_by_severity"]["error"] = 3
    report["summary"]["mods_with_conflicts"] = 3
    _show_report_and_wait(qtbot, dialog, report)

    dialog.inspector.raw_button.click()
    dialog.inspector.technical_button.click()
    assert dialog.inspector.raw_view.toPlainText()
    assert dialog.inspector._details_layout.count() > 0

    dialog.table.selectRow(2)

    assert dialog.conflict_model.source_row(dialog.table.currentIndex()) == 4
    assert dialog.inspector.raw_view.toPlainText() == ""
    assert not dialog.inspector.raw_button.isChecked()
    assert not dialog.inspector.technical_button.isChecked()
    assert dialog.inspector._details_layout.count() == 0


def test_replacing_selected_finding_retires_old_mod_actions_before_raw_clear(
    raw_triage_dialog: RawTriageDialog,
) -> None:
    dialog, report, _ = raw_triage_dialog
    old_button = next(
        button
        for button in _mod_action_buttons(dialog)
        if "example.b" in _button_text(button)
    )
    received: list[str] = []
    observed: list[tuple[bool, bool]] = []
    dialog.inspector.mod_requested.connect(received.append)

    def on_raw_clear() -> None:
        if observed:
            return
        observed.append(
            (
                dialog.inspector._finding is report["conflicts"][3],
                old_button.isEnabled(),
            )
        )
        old_button.click()

    dialog.inspector.raw_view.textChanged.connect(on_raw_clear)
    dialog.table.selectRow(1)

    assert observed == [(True, False)]
    assert received == []
    assert (
        dialog.conflict_model.finding(dialog.table.currentIndex())
        is report["conflicts"][3]
    )


@pytest.mark.parametrize("open_new_raw", [False, True])
def test_raw_clear_reselection_preserves_latest_selection(
    raw_triage_dialog: RawTriageDialog, open_new_raw: bool
) -> None:
    dialog, report, inspector = raw_triage_dialog
    fired: list[bool] = []

    def reselect() -> None:
        if fired:
            return
        fired.append(True)
        dialog.table.selectRow(0)
        if open_new_raw:
            inspector.raw_button.click()
            inspector.technical_button.click()

    inspector.raw_view.textChanged.connect(reselect)
    dialog.table.selectRow(1)

    assert fired == [True]
    assert dialog.table.currentIndex().row() == 0
    assert inspector._finding is report["conflicts"][1]
    assert inspector._target_label.text() == "ThingDef: Shared"
    assert "example.b" in inspector.outcome_label.text()
    active_buttons = [b for b in _mod_action_buttons(dialog) if b.isEnabled()]
    assert [_button_text(b) for b in active_buttons] == [
        "A (example.a)",
        "B (example.b)",
    ]
    if open_new_raw:
        assert inspector.raw_button.isChecked()
        assert inspector.raw_view.isVisible()
        assert inspector.raw_button.text() == "Hide raw finding data"
        assert inspector.technical_button.isChecked()
        assert inspector._details_widget.isVisible()
        assert inspector._details_layout.count() > 0
        assert json.loads(inspector.raw_view.toPlainText()) == report["conflicts"][1]
    else:
        assert not inspector.raw_button.isChecked()
        assert inspector.raw_view.toPlainText() == ""
        inspector.raw_button.click()
        assert json.loads(inspector.raw_view.toPlainText()) == report["conflicts"][1]


def test_raw_open_reselection_preserves_newer_closed_state(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = _show_visible_triage_report(qtbot, dialog)
    inspector = dialog.inspector
    fired: list[bool] = []

    def reselect() -> None:
        if not fired:
            fired.append(True)
            dialog.table.selectRow(1)

    inspector.raw_view.textChanged.connect(reselect)
    inspector.raw_button.click()
    assert fired == [True]
    assert inspector._finding is report["conflicts"][3]
    assert inspector._target_label.text() == "Verse.Pawn.Tick"
    assert not inspector.raw_button.isChecked()
    assert inspector.raw_view.toPlainText() == ""
    assert not inspector.raw_view.isVisible()


def test_raw_close_reselection_preserves_newer_open_state(
    raw_triage_dialog: RawTriageDialog,
) -> None:
    dialog, report, inspector = raw_triage_dialog
    fired: list[bool] = []

    def reselect() -> None:
        if fired:
            return
        fired.append(True)
        dialog.table.selectRow(1)
        inspector.raw_button.click()

    inspector.raw_view.textChanged.connect(reselect)
    inspector.raw_button.click()
    assert fired == [True]
    assert inspector._finding is report["conflicts"][3]
    assert inspector._target_label.text() == "Verse.Pawn.Tick"
    assert inspector.raw_button.isChecked()
    assert inspector.raw_view.isVisible()
    assert json.loads(inspector.raw_view.toPlainText()) == report["conflicts"][3]


def test_focus_reselection_preserves_new_disclosures_and_retires_actions(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = _show_visible_triage_report(qtbot, dialog)
    dialog.activateWindow()
    inspector = dialog.inspector
    old_buttons = list(inspector._mod_buttons)
    old_button = old_buttons[0]
    old_button.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is old_button)
    fired: list[bool] = []
    received: list[object] = []
    nested: list[tuple[bool, bool]] = []
    inspector.mod_requested.connect(received.append)

    def on_focus_changed(old: object, _new: object) -> None:
        if old is old_button and not fired:
            fired.append(True)
            old_buttons[1].click()
            dialog.table.selectRow(0)
            inspector.technical_button.click()
            inspector.raw_button.click()
            nested.append(
                (
                    inspector.technical_button.isChecked(),
                    inspector.raw_button.isChecked(),
                )
            )

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    app.focusChanged.connect(on_focus_changed)
    try:
        dialog.table.selectRow(1)
        assert fired == [True]
        assert nested == [(True, True)]
        assert dialog.table.currentIndex().row() == 0
        assert inspector._finding is report["conflicts"][1]
        assert inspector._target_label.text() == "ThingDef: Shared"
        assert "example.b" in inspector.outcome_label.text()
        assert received == []
        assert [_button_text(button) for button in inspector._mod_buttons] == [
            "A (example.a)",
            "B (example.b)",
        ]
        for button in old_buttons:
            button.click()
        assert received == []
        qtbot.waitUntil(
            lambda: all(button.isVisible() for button in inspector._mod_buttons)
        )
        assert all(button.isEnabled() for button in inspector._mod_buttons)
        assert inspector.technical_button.isChecked()
        assert inspector._details_layout.count() > 0
        assert inspector.raw_button.isChecked()
        assert inspector.raw_view.isVisible()
        assert json.loads(inspector.raw_view.toPlainText()) == report["conflicts"][1]
    finally:
        app.focusChanged.disconnect(on_focus_changed)


def test_selection_raw_clear_allows_new_finding_raw_open(
    raw_triage_dialog: RawTriageDialog,
) -> None:
    dialog, report, inspector = raw_triage_dialog
    fired: list[bool] = []

    def open_raw() -> None:
        if not fired:
            fired.append(True)
            inspector.raw_button.click()

    inspector.raw_view.textChanged.connect(open_raw)
    dialog.table.selectRow(1)
    assert fired == [True]
    assert inspector._finding is report["conflicts"][3]
    assert inspector._target_label.text() == "Verse.Pawn.Tick"
    assert "Def-style winner" in inspector.outcome_label.text()
    assert inspector.raw_button.isChecked()
    assert inspector.raw_button.text() == "Hide raw finding data"
    assert inspector.raw_view.isVisible()
    assert json.loads(inspector.raw_view.toPlainText()) == report["conflicts"][3]


@pytest.mark.parametrize("initially_open", [False, True])
def test_nested_raw_toggle_wins_without_selection_change(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner], initially_open: bool
) -> None:
    dialog, _, _ = dialog_setup
    report = _show_visible_triage_report(qtbot, dialog)
    inspector = dialog.inspector
    if initially_open:
        inspector.raw_button.click()
    fired: list[bool] = []

    def toggle_again() -> None:
        if not fired:
            fired.append(True)
            inspector.raw_button.click()

    inspector.raw_view.textChanged.connect(toggle_again)
    inspector.raw_button.click()
    assert fired == [True]
    assert inspector._finding is report["conflicts"][1]
    assert inspector.raw_button.isChecked() is initially_open
    assert inspector.raw_view.isVisible() is initially_open
    if initially_open:
        assert inspector.raw_button.text() == "Hide raw finding data"
        assert json.loads(inspector.raw_view.toPlainText()) == report["conflicts"][1]
    else:
        assert inspector.raw_button.text() == "Show raw finding data"
        assert inspector.raw_view.toPlainText() == ""


def test_inspector_shows_unknown_winner_and_condition_when_absent(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    _show_report_and_wait(qtbot, dialog, report)

    dialog.severity_buttons["error"].click()
    _wait_for_view(qtbot, dialog)
    dialog.severity_buttons["warning"].click()
    _wait_for_view(qtbot, dialog)

    assert (
        dialog.conflict_model.finding(dialog.table.currentIndex())
        is report["conflicts"][2]
    )
    assert dialog.tr("Winner") in dialog.inspector.outcome_label.text()
    assert dialog.tr("Condition") in dialog.inspector.outcome_label.text()
    assert dialog.tr("Unknown") in dialog.inspector.outcome_label.text()


@pytest.mark.parametrize("reselect", [False, True])
@pytest.mark.parametrize(
    ("package_id", "name", "button_text"),
    [("example.\udcff", "B", "example.\\udcff"), ("", "Empty ID", "Empty ID")],
)
def test_mod_link_uses_existing_filter_with_captured_package_id(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    package_id: str,
    name: str,
    button_text: str,
    reselect: bool,
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    target_mod = report["conflicts"][1]["mods"][1]
    target_mod["package_id"] = package_id
    target_mod["name"] = name
    _show_report_and_wait(qtbot, dialog, report)
    if reselect:
        dialog.table.selectRow(1)
        dialog.table.selectRow(0)
        assert dialog.inspector._finding is report["conflicts"][1]
    button = next(
        button
        for button in _mod_action_buttons(dialog)
        if button_text in _button_text(button)
    )

    received: list[object] = []
    dialog.inspector.mod_requested.connect(received.append)
    button.click()
    _wait_for_view(qtbot, dialog)

    assert dialog.browser.filters.package_id == package_id
    assert received and received[0] is target_mod["package_id"]


def test_inspector_mod_actions_disable_while_findings_update(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    force_one_row_per_tick(monkeypatch)
    _show_report_and_wait(qtbot, dialog, make_triage_report())

    buttons = _mod_action_buttons(dialog)
    assert buttons
    assert all(button.isEnabled() for button in buttons)

    dialog.severity_buttons["all"].click()

    assert dialog.browser.busy
    assert all(not button.isEnabled() for button in _mod_action_buttons(dialog))
    assert dialog.finding_search.isEnabled()
    assert dialog.type_filter.isEnabled()
    assert dialog.reset_filters_button.isEnabled()
    assert _close_button(dialog).isEnabled()

    _wait_for_view(qtbot, dialog)
    assert all(button.isEnabled() for button in _mod_action_buttons(dialog))


def test_no_matching_filters_clear_the_inspector(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    _show_report_and_wait(qtbot, dialog, make_triage_report())
    dialog.inspector.raw_button.click()
    dialog.inspector.technical_button.click()
    assert dialog.inspector.raw_view.toPlainText()

    dialog.finding_search.setText("no such finding")
    _wait_for_view(qtbot, dialog)

    assert dialog.conflict_model.rowCount() == 0
    assert dialog.inspector.outcome_label.text() == ""
    assert dialog.inspector.raw_view.toPlainText() == ""
    assert not dialog.inspector.raw_button.isChecked()
    assert not dialog.inspector.raw_button.isEnabled()
    assert not dialog.inspector.technical_button.isChecked()
    assert not dialog.inspector.technical_button.isEnabled()
    assert dialog.inspector._details_layout.count() == 0


def test_scan_notes_do_not_eagerly_format_all_diagnostics(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.windows import conflict_report_dialog

    formatted: list[dict[str, Any]] = []
    original = conflict_report_dialog._diagnostic_message

    def spy(diagnostic: dict[str, Any]) -> str:
        formatted.append(diagnostic)
        return original(diagnostic)

    monkeypatch.setattr(conflict_report_dialog, "_diagnostic_message", spy)
    widget, _, _ = make_two_mod_list(qtbot, tmp_path)
    metadata = FakeMetadata(widget.metadata_controller)
    widget.metadata_controller = cast(MetadataController, metadata)
    snapshot = snapshot_active_mods(widget, widget.metadata_controller, "instance-a")
    dialog = ConflictReportDialog(
        widget, widget.metadata_controller, lambda: "instance-a", snapshot, FakeRunner()
    )
    qtbot.addWidget(dialog)
    report = make_triage_report()
    report["diagnostics"] = [
        {
            "severity": "info",
            "source": "xml_parsing",
            "analysis_incomplete": False,
            "message": f"ordinary {index}",
            "affected_mod": None,
        }
        for index in range(4)
    ]
    dialog.show_report(report)
    assert formatted == []
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    assert formatted == []

    dialog.notes.show_info.setChecked(True)
    dialog.notes.table.selectRow(0)
    assert report["diagnostics"][0] in formatted
    assert "ordinary 0" in dialog.notes.details_view.toPlainText()


def test_scan_notes_hide_ordinary_info_by_default(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, _, _ = dialog_setup
    report = make_report("error", False)
    report["diagnostics"][0]["message"] = "ordinary information marker"
    dialog.show_report(report)
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    assert dialog.notes.model.rowCount() == 0
    dialog.notes.show_info.setChecked(True)
    assert dialog.notes.model.rowCount() == 1
    dialog.notes.table.selectRow(0)
    assert "ordinary information marker" in dialog.notes.details_view.toPlainText()


def test_notes_remain_scan_wide_and_badge_opens_without_changing_filters(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, runner = dialog_setup
    report = make_report("error", False)
    report["diagnostics"] = make_notes_diagnostics()
    dialog.show_report(report)
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    assert dialog.notes.model.attention_count == 3
    assert dialog.notes.model.rowCount() == 3
    assert dialog.is_incomplete
    dialog.finding_search.setText("no matching finding")
    _wait_for_view(qtbot, dialog)
    assert dialog.conflict_model.rowCount() == 0
    assert dialog.notes.model.rowCount() == 3
    filters = dialog.browser.filters
    dialog.incomplete_badge.click()
    assert dialog.tabs.currentWidget() is dialog.notes
    assert dialog.browser.filters == filters
    assert runner.start_calls == 1
    assert not dialog.is_stale
    dialog.notes.show_info.setChecked(True)
    assert dialog.notes.model.rowCount() == 4
    assert [
        dialog.notes.model._record(
            dialog.notes.model.note(dialog.notes.model.index(i, 0))
        )
        is report["diagnostics"][i]
        for i in range(4)
    ] == [True] * 4


def test_notes_count_is_preparing_until_complete(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    report = make_report("error", False)
    report["diagnostics"] = make_notes_diagnostics()
    force_one_row_per_tick(monkeypatch)
    observed: list[tuple[str, bool, int | None]] = []

    def observe_partial() -> None:
        if dialog.notes.model._index == 1 and not observed:
            observed.append(
                (
                    dialog.incomplete_badge.text(),
                    dialog.incomplete_badge.isHidden(),
                    dialog.notes.model.attention_count,
                )
            )

    dialog.notes.model._timer.timeout.connect(observe_partial)
    dialog.show_report(report)
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    assert len(observed) == 1
    text, hidden, count = observed[0]
    assert "…" in text
    assert "Preparing" in text
    assert not hidden
    assert count is None
    assert "3" in dialog.incomplete_badge.text()


def _complete_scan_notes_report(*, include_info: bool) -> dict[str, Any]:
    report = make_report("error", False)
    report["diagnostics"] = [
        {
            "source": "xml_parsing",
            "severity": "warning",
            "analysis_incomplete": False,
            "message": "warning",
            "affected_mod": None,
        },
        {
            "source": "dll_parsing",
            "severity": "error",
            "analysis_incomplete": False,
            "message": "error",
            "affected_mod": None,
        },
    ]
    if include_info:
        report["diagnostics"].append(
            {
                "source": "metadata_resolution",
                "severity": "info",
                "analysis_incomplete": False,
                "message": "ordinary",
                "affected_mod": None,
            }
        )
    return report


def test_notes_tab_shows_attention_count_without_incomplete_badge(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = _complete_scan_notes_report(include_info=True)
    notes_tab = dialog.tabs.indexOf(dialog.notes)

    dialog.show_report(report)
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)

    expected = dialog.tr("Scan notes: {count}").format(count=dialog._format_count(2))
    assert not dialog.is_incomplete
    assert dialog.incomplete_badge.isHidden()
    assert dialog.tabs.tabText(notes_tab) == expected

    dialog.finding_search.setText("no matching finding")
    _wait_for_view(qtbot, dialog)
    dialog.notes.show_info.setChecked(True)

    assert dialog.notes.model.attention_count == 2
    assert dialog.notes.model.rowCount() == 3
    assert dialog.tabs.tabText(notes_tab) == expected
    assert dialog.incomplete_badge.isHidden()


def test_notes_tab_shows_unready_marker_until_attention_count_completes(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    report = _complete_scan_notes_report(include_info=False)
    notes_tab = dialog.tabs.indexOf(dialog.notes)
    force_one_row_per_tick(monkeypatch)
    observed: list[tuple[str, int | None]] = []

    def observe_partial() -> None:
        if dialog.notes.model._index == 1 and not observed:
            observed.append(
                (dialog.tabs.tabText(notes_tab), dialog.notes.model.attention_count)
            )

    dialog.notes.model._timer.timeout.connect(observe_partial)
    dialog.show_report(report)
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)

    assert observed == [(dialog.tr("Scan notes: {count}").format(count="…"), None)]


def test_notes_source_labels_use_translated_human_readable_names(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner], tmp_path: Path
) -> None:
    dialog, _, _ = dialog_setup
    app, translator = _install_translator(
        tmp_path,
        "note-sources",
        '<TS version="2.1" language="fr"><context><name>ConflictReportDialog</name>'
        "<message><source>XML parsing</source><translation>Analyse XML</translation></message>"
        "</context></TS>",
    )
    try:
        report = make_report("warning", False)
        report["diagnostics"][0]["severity"] = "warning"
        dialog.show_report(report)
        _select_note(qtbot, dialog, "native")
        assert dialog.notes.model.data(dialog.notes.model.index(0, 0)) == "Analyse XML"
        assert "Analyse XML" in dialog.notes.details_view.toPlainText()
    finally:
        app.removeTranslator(translator)


@pytest.mark.parametrize("path", ["/mods/example/LoadFolders.xml", None])
def test_loadfolders_note_optional_path_preserves_message_and_raw(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner], path: str | None
) -> None:
    dialog, _, _ = dialog_setup
    dialog.show()
    report = make_report("warning", False)
    record = report["diagnostics"][0]
    params = {"detail": "broken XML"}
    if path is not None:
        params["path"] = path
    record.update(
        code="load_folders_parse_failure",
        params=params,
        message="native fallback",
        severity="warning",
    )
    dialog.show_report(report)
    _select_note(qtbot, dialog, "native")
    text = dialog.notes.details_view.toPlainText()
    assert _diagnostic_message(record) in text
    if path is None:
        assert "\nPath:" not in text
    else:
        assert f"\nPath: {path}" in text
    assert dialog.notes.raw_view.toPlainText() == ""
    dialog.notes.raw_button.click()
    assert json.loads(dialog.notes.raw_view.toPlainText()) == record


def test_notes_raw_disclosure_is_lazy_and_preserves_original_record(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.views import conflict_report_details

    dialog, _, _ = dialog_setup
    report = make_report("error", False)
    record = report["diagnostics"][0]
    record.update(
        severity="warning", message="猫 <tag> invalid-\udcff", affected_mod="Mód"
    )
    calls: list[object] = []
    dumps = conflict_report_details.json.dumps

    def spy(value: object, **kwargs: Any) -> str:
        calls.append(value)
        return dumps(value, **kwargs)

    monkeypatch.setattr(conflict_report_details.json, "dumps", spy)
    dialog.show_report(report)
    _select_note(qtbot, dialog, "native")
    assert not any(value is record for value in calls)
    assert "猫 <tag> invalid-\\udcff" in dialog.notes.details_view.toPlainText()
    assert "Mód" in dialog.notes.details_view.toPlainText()
    assert dialog.notes.raw_view.toPlainText() == ""
    dialog.notes.raw_button.click()
    assert sum(value is record for value in calls) == 1
    assert json.loads(dialog.notes.raw_view.toPlainText()) == record
    dialog.notes.table.clearSelection()
    dialog.notes.table.setCurrentIndex(dialog.notes.model.index(-1, -1))
    assert dialog.notes.raw_view.toPlainText() == ""
    assert not dialog.notes.raw_button.isChecked()
    assert not dialog.notes.raw_button.isEnabled()


def _open_warning_note_raw(qtbot: Any, dialog: ConflictReportDialog) -> None:
    report = make_report("error", False)
    report["diagnostics"][0]["severity"] = "warning"
    dialog.show_report(report)
    _select_note(qtbot, dialog, "native")
    dialog.notes.raw_button.click()


def test_disposed_notes_ignore_late_raw_toggle(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    _open_warning_note_raw(qtbot, dialog)
    raw = dialog.notes.raw_view.toPlainText()
    assert raw
    dialog.accept()
    changes: list[str] = []
    dialog.notes.raw_view.textChanged.connect(lambda: changes.append("changed"))
    dialog.notes.raw_button.setChecked(False)
    assert changes == []
    assert dialog.notes.raw_view.toPlainText() == raw


def test_notes_filter_reset_clears_selection_and_raw(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    _open_warning_note_raw(qtbot, dialog)
    assert dialog.notes.raw_view.toPlainText()
    dialog.notes.show_info.setChecked(True)
    assert dialog.notes.raw_view.toPlainText() == ""
    assert dialog.notes.details_view.toPlainText() == ""
    assert not dialog.notes.raw_button.isEnabled()


def test_notes_synthetic_records_are_individually_addressable(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    from app.services.conflict_snapshot import InputIssue, ScanSnapshot

    dialog, _, _ = dialog_setup
    snapshot = ScanSnapshot(
        (),
        None,
        "instance",
        (
            InputIssue("first issue", "/full/<path>"),
            InputIssue("second issue", "bad-\udcff"),
        ),
    )
    diagnostics = [
        {
            "severity": "warning",
            "source": source,
            "analysis_incomplete": False,
            "message": message,
            "affected_mod": None,
        }
        for source, message in (
            ("dll_parsing", "dll 1"),
            ("xml_parsing", "xml"),
            ("dll_parsing", "dll 2"),
        )
    ]
    dialog.notes.set_notes(snapshot, diagnostics, "terminal failure")
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    model = dialog.notes.model
    assert model.attention_count == 7
    assert [
        (model.note(model.index(i, 0)).kind, model.note(model.index(i, 0)).index)
        for i in range(7)
    ] == [
        ("input", 0),
        ("input", 1),
        ("version", 0),
        ("native", 1),
        ("native", 0),
        ("native", 2),
        ("failure", 0),
    ]
    _select_note(qtbot, dialog, "input", 0)
    assert "first issue: /full/<path>" in dialog.notes.details_view.toPlainText()
    _select_note(qtbot, dialog, "input", 1)
    assert "second issue: bad-\\udcff" in dialog.notes.details_view.toPlainText()
    _select_note(qtbot, dialog, "version")
    assert "Unknown game version" in dialog.notes.details_view.toPlainText()
    _select_note(qtbot, dialog, "failure")
    assert "terminal failure" in dialog.notes.details_view.toPlainText()


def test_accept_during_notes_progress_stops_late_publication(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, runner = dialog_setup
    force_one_row_per_tick(monkeypatch)
    diagnostic = {
        "severity": "warning",
        "source": "xml_parsing",
        "analysis_incomplete": False,
        "message": "pending",
        "affected_mod": None,
    }
    events: list[str] = []
    dialog.notes.model.prepared.connect(lambda: events.append("prepared"))

    def accept_mid_scan() -> None:
        if dialog.notes.model._index == 1 and not events:
            events.append("accepted")
            dialog.accept()

    dialog.notes.model._timer.timeout.connect(accept_mid_scan)
    dialog.notes.set_notes(dialog.snapshot, [diagnostic] * 8)
    qtbot.waitUntil(lambda: "accepted" in events)
    qtbot.wait(10)
    assert events == ["accepted"]
    assert not dialog.notes.model.busy
    assert runner.cancel_calls == 1
    assert dialog.notes.model.rowCount() == 0


def test_default_view_is_severity_first(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()

    dialog.show_report(report)

    _wait_for_view(qtbot, dialog)
    assert dialog.report is report
    assert dialog.conflict_model.conflicts is report["conflicts"]
    assert dialog.browser.filters.severities == frozenset({"error"})
    assert list(dialog.conflict_model.source_rows) == [1, 3]
    assert (
        dialog.conflict_model.finding(dialog.conflict_model.index(0, 0))
        is report["conflicts"][1]
    )


@pytest.mark.parametrize(
    ("counts", "expected_severity", "expected_rows", "expected_empty"),
    [
        ((2, 1, 1), frozenset({"error"}), [1, 3], False),
        ((0, 1, 1), frozenset({"warning"}), [1], False),
        ((0, 0, 1), frozenset({"info"}), [0], False),
        ((0, 0, 0), frozenset({"error", "warning", "info"}), [], True),
    ],
)
def test_highest_nonempty_default(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    counts: tuple[int, int, int],
    expected_severity: frozenset[str],
    expected_rows: list[int],
    expected_empty: bool,
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report_with_counts(*counts)

    dialog.show_report(report)

    _wait_for_view(qtbot, dialog)
    assert dialog.browser.filters.severities == expected_severity
    assert list(dialog.conflict_model.source_rows) == expected_rows
    assert dialog.empty_label.isHidden() is (not expected_empty)
    if expected_empty:
        assert dialog.empty_label.text() == dialog.tr("No findings reported.")


def test_severity_selection(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    dialog.show_report(report)
    _wait_for_view(qtbot, dialog)

    dialog.severity_buttons["all"].click()

    _wait_for_view(qtbot, dialog)
    assert list(dialog.conflict_model.source_rows) == [1, 3, 2, 0]
    assert dialog.empty_label.isHidden()

    dialog.severity_buttons["error"].click()
    _wait_for_view(qtbot, dialog)
    dialog.severity_buttons["warning"].click()
    _wait_for_view(qtbot, dialog)
    dialog.severity_buttons["info"].click()
    _wait_for_view(qtbot, dialog)
    assert dialog.conflict_model.rowCount() == 0
    assert dialog.empty_label.text() == dialog.tr("Choose at least one severity.")


def test_preparation_state(
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, _, _ = dialog_setup

    dialog.show_report(make_triage_report())

    assert dialog.browser.busy
    assert dialog.empty_label.text() == dialog.tr("Preparing findings…")
    assert dialog.conflict_model.rowCount() == 0


def test_close_invalidates_preparation(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    force_one_row_per_tick(monkeypatch)
    published: list[list[int]] = []
    dialog.browser.applied.connect(
        lambda view: published.append(list(view.source_rows))
    )

    dialog.show_report(make_triage_report())
    dialog.close()
    _process_next_event_turn(qtbot)

    assert not dialog.browser.busy
    assert published == []
    assert dialog.conflict_model.rowCount() == 0


def test_superseded_report_never_publishes_old_rows(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    force_one_row_per_tick(monkeypatch)
    first_report = make_triage_report()
    second_report = make_triage_report_with_counts(0, 1, 1)
    publications: list[list[int]] = []
    dialog.browser.applied.connect(
        lambda view: publications.append(list(view.source_rows))
    )

    dialog.show_report(first_report)
    QCoreApplication.processEvents()
    dialog.show_report(second_report)
    _process_next_event_turn(qtbot)

    _wait_for_view(qtbot, dialog)
    assert dialog.report is second_report
    assert dialog.conflict_model.conflicts is second_report["conflicts"]
    assert publications == [[1]]
    assert list(dialog.conflict_model.source_rows) == [1]
    assert (
        dialog.conflict_model.finding(dialog.conflict_model.index(0, 0))
        is second_report["conflicts"][1]
    )


def test_reset_clears_prior_browser_package_before_query(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    _start_report_preparation(dialog, monkeypatch, make_triage_report())

    dialog.browser.set_filters(
        FindingFilters(
            frozenset({"error", "warning", "info"}),
            package_id="example.c",
        )
    )
    dialog.reset_filters_button.click()
    post_reset_package = dialog.browser.filters.package_id
    post_reset_query = dialog.browser.filters.query
    post_reset_type = dialog.browser.filters.finding_type

    dialog.finding_search.setText("Shared")
    _wait_for_view(qtbot, dialog)

    assert (
        post_reset_package,
        post_reset_query,
        post_reset_type,
        dialog.browser.filters.package_id,
        dialog.browser.filters.query,
        dialog.browser.filters.finding_type,
        list(dialog.conflict_model.source_rows),
    ) == (None, "", None, None, "Shared", None, [1, 0])


def test_later_browser_request_supersedes_pending_reset(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    _start_report_preparation(dialog, monkeypatch, make_triage_report())
    requested_filters = FindingFilters(frozenset({"warning"}), query="Other")

    dialog.reset_filters_button.click()
    dialog.browser.set_filters(requested_filters)
    assert dialog.browser.filters == requested_filters

    _wait_for_view(qtbot, dialog)

    assert dialog.browser.filters == requested_filters
    assert list(dialog.conflict_model.source_rows) == [2]


def test_reentrant_report_reset_uses_replacement_default(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, _, _ = dialog_setup
    replacement_report = make_triage_report_with_counts(0, 1, 1)
    model_reset_hits = 0

    assert [finding["severity"] for finding in replacement_report["conflicts"]] == [
        "info",
        "warning",
    ]

    def replace_during_model_reset() -> None:
        nonlocal model_reset_hits
        if model_reset_hits or not dialog.browser.mods:
            return
        model_reset_hits += 1
        dialog.show_report(replacement_report)
        dialog.reset_filters_button.click()

    dialog.mod_model.modelReset.connect(replace_during_model_reset)

    dialog.show_report(make_triage_report())
    _wait_for_view(qtbot, dialog)

    assert model_reset_hits == 1
    assert dialog.report is replacement_report
    assert dialog.browser.initial_filters.severities == frozenset({"warning"})
    assert dialog.browser.filters.severities == frozenset({"warning"})
    assert list(dialog.conflict_model.source_rows) == [1]


def test_reset_model_reset_callback_preserves_later_browser_request(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, _, _ = dialog_setup
    requested_filters = FindingFilters(frozenset({"warning"}), query="Other")
    model_reset_hits: list[bool]

    _show_report_and_wait(qtbot, dialog, make_triage_report())

    def request_during_reset_entry() -> None:
        dialog.browser.set_filters(requested_filters)

    model_reset_hits = _observe_next_mod_model_reset(dialog, request_during_reset_entry)

    dialog.reset_filters_button.click()
    _wait_for_view(qtbot, dialog)

    assert len(model_reset_hits) == 1
    assert dialog.browser.filters == requested_filters
    assert list(dialog.conflict_model.source_rows) == [2]


def test_reset_model_reset_callback_preserves_replacement_request(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, _, _ = dialog_setup
    replacement_report = make_triage_report_with_counts(0, 1, 1)
    requested_filters = FindingFilters(frozenset({"info"}), query="Shared")
    model_reset_hits: list[bool]

    assert [finding["severity"] for finding in replacement_report["conflicts"]] == [
        "info",
        "warning",
    ]
    _show_report_and_wait(qtbot, dialog, make_triage_report())

    def replace_during_reset_entry() -> None:
        dialog.show_report(replacement_report)
        dialog.browser.set_filters(requested_filters)

    model_reset_hits = _observe_next_mod_model_reset(dialog, replace_during_reset_entry)

    dialog.reset_filters_button.click()
    _wait_for_view(qtbot, dialog)

    assert len(model_reset_hits) == 1
    assert dialog.report is replacement_report
    assert dialog.browser.filters == requested_filters
    assert list(dialog.conflict_model.source_rows) == [0]


@pytest.mark.parametrize("starting_severity", ["error", "warning"])
def test_reset_busy_callback_observes_cleared_controls_and_preserves_search(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    starting_severity: str,
) -> None:
    dialog, _, _ = dialog_setup
    _show_report_and_wait(qtbot, dialog, make_triage_report())
    if starting_severity == "warning":
        dialog.severity_buttons["warning"].click()
        dialog.severity_buttons["error"].click()
        _wait_for_view(qtbot, dialog)
    dialog.type_filter.setCurrentIndex(dialog.type_filter.findData("harmony"))
    _wait_for_view(qtbot, dialog)
    assert dialog.browser.filters == FindingFilters(
        frozenset({starting_severity}), finding_type="harmony"
    )
    assert _checked_severities(dialog) == frozenset({starting_severity})
    assert dialog.type_filter.currentData() == "harmony"
    assert not dialog.browser.busy
    observations: list[tuple[FindingFilters, object, frozenset[str]]] = []

    def on_busy(busy: bool) -> None:
        if not busy or observations:
            return
        observations.append(
            (
                dialog.browser.filters,
                dialog.type_filter.currentData(),
                _checked_severities(dialog),
            )
        )
        dialog.finding_search.setText("Shared")
        dialog.mod_search.setText("example.a")

    dialog.browser.busy_changed.connect(on_busy)
    dialog.reset_filters_button.click()
    _wait_for_view(qtbot, dialog)

    assert {
        "observations": observations,
        "filters": dialog.browser.filters,
        "rows": list(dialog.conflict_model.source_rows),
        "sidebar_text": dialog.mod_search.text(),
        "sidebar_mods": _visible_sidebar_package_ids(dialog),
    } == {
        "observations": [
            (FindingFilters(frozenset({"error"})), None, frozenset({"error"}))
        ],
        "filters": FindingFilters(frozenset({"error"}), query="Shared"),
        "rows": [1],
        "sidebar_text": "example.a",
        "sidebar_mods": ["example.a"],
    }


def test_reset_busy_callback_preserves_replacement_request_and_sidebar_search(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, _, _ = dialog_setup
    replacement = make_triage_report_with_counts(0, 1, 1)
    assert [finding["severity"] for finding in replacement["conflicts"]] == [
        "info",
        "warning",
    ]
    _show_report_and_wait(qtbot, dialog, make_triage_report())
    assert not dialog.browser.busy
    hits: list[bool] = []
    requested = FindingFilters(frozenset({"info"}), query="Shared")

    def on_busy(busy: bool) -> None:
        if not busy or hits:
            return
        hits.append(True)
        dialog.show_report(replacement)
        dialog.browser.set_filters(requested)
        dialog.mod_search.setText("example.b")

    dialog.browser.busy_changed.connect(on_busy)
    dialog.reset_filters_button.click()
    _wait_for_view(qtbot, dialog)

    assert hits == [True]
    assert dialog.report is replacement
    assert dialog.browser.conflicts is replacement["conflicts"]
    assert dialog.conflict_model.conflicts is replacement["conflicts"]
    assert {
        "filters": dialog.browser.filters,
        "rows": list(dialog.conflict_model.source_rows),
        "sidebar_text": dialog.mod_search.text(),
        "sidebar_mods": _visible_sidebar_package_ids(dialog),
    } == {
        "filters": requested,
        "rows": [0],
        "sidebar_text": "example.b",
        "sidebar_mods": ["example.b"],
    }


def test_reset_busy_callback_close_prevents_post_teardown_model_reset(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, _, _ = dialog_setup
    _show_report_and_wait(qtbot, dialog, make_triage_report())
    assert not dialog.browser.busy
    hits: list[bool] = []
    resets_after_teardown: list[bool] = []
    publications_after_teardown: list[object] = []

    def close_on_busy(busy: bool) -> None:
        if not busy or hits:
            return
        hits.append(True)
        dialog.close()

    def record_reset() -> None:
        if dialog._teardown_complete:
            resets_after_teardown.append(True)

    def record_publication(view: object) -> None:
        if dialog._teardown_complete:
            publications_after_teardown.append(view)

    dialog.mod_model.modelReset.connect(record_reset)
    dialog.browser.applied.connect(record_publication)
    dialog.browser.busy_changed.connect(close_on_busy)
    dialog.reset_filters_button.click()
    _process_next_event_turn(qtbot)

    assert hits == [True]
    assert dialog._teardown_complete
    assert dialog.browser._disposed
    assert not dialog.browser.busy
    assert publications_after_teardown == []
    assert resets_after_teardown == []


def _settle_warning_only(qtbot: Any, dialog: ConflictReportDialog) -> dict[str, Any]:
    report = make_triage_report()
    _show_report_and_wait(qtbot, dialog, report)
    dialog.severity_buttons["warning"].click()
    dialog.severity_buttons["error"].click()
    _wait_for_view(qtbot, dialog)
    assert dialog.browser.filters == FindingFilters(frozenset({"warning"}))
    return report


def _observe_reset_and_enter_shared(
    dialog: ConflictReportDialog,
) -> tuple[list[bool], list[tuple[FindingFilters, frozenset[str], str, object]]]:
    boundary: list[tuple[FindingFilters, frozenset[str], str, object]] = []

    def enter_shared() -> None:
        boundary.append(
            (
                dialog.browser.filters,
                _checked_severities(dialog),
                dialog.finding_search.text(),
                dialog.type_filter.currentData(),
            )
        )
        dialog.finding_search.setText("Shared")

    return _observe_next_mod_model_reset(dialog, enter_shared), boundary


def test_reset_while_busy_projects_current_filters_before_model_reset(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = _settle_warning_only(qtbot, dialog)
    dialog.finding_search.setText("Other")
    assert dialog.browser.filters == FindingFilters(
        frozenset({"warning"}), query="Other"
    )
    assert dialog.browser.busy
    hits, boundary = _observe_reset_and_enter_shared(dialog)
    assert dialog.browser.busy
    dialog.reset_filters_button.click()
    _wait_for_view(qtbot, dialog)

    assert dialog.report is report
    assert dialog.browser.conflicts is report["conflicts"]
    assert dialog.conflict_model.conflicts is report["conflicts"]
    assert {
        "hits": hits,
        "boundary": boundary,
        "filters": dialog.browser.filters,
        "rows": list(dialog.conflict_model.source_rows),
    } == {
        "hits": [True],
        "boundary": [
            (FindingFilters(frozenset({"error"})), frozenset({"error"}), "", None)
        ],
        "filters": FindingFilters(frozenset({"error"}), query="Shared"),
        "rows": [1],
    }


def test_reset_projects_newer_busy_request_before_model_reset(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = _settle_warning_only(qtbot, dialog)
    assert not dialog.browser.busy
    requested = FindingFilters(frozenset({"warning"}), query="Other")
    busy_hits: list[bool] = []

    def request_on_busy(busy: bool) -> None:
        if not busy or busy_hits:
            return
        busy_hits.append(True)
        dialog.browser.set_filters(requested)

    dialog.browser.busy_changed.connect(request_on_busy)
    reset_hits, boundary = _observe_reset_and_enter_shared(dialog)
    dialog.reset_filters_button.click()
    _wait_for_view(qtbot, dialog)

    assert dialog.report is report
    assert dialog.browser.conflicts is report["conflicts"]
    assert dialog.conflict_model.conflicts is report["conflicts"]
    assert {
        "busy_hits": busy_hits,
        "reset_hits": reset_hits,
        "boundary": boundary,
        "filters": dialog.browser.filters,
        "rows": list(dialog.conflict_model.source_rows),
    } == {
        "busy_hits": [True],
        "reset_hits": [True],
        "boundary": [(requested, frozenset({"warning"}), "Other", None)],
        "filters": FindingFilters(frozenset({"warning"}), query="Shared"),
        "rows": [],
    }


def test_reset_preserves_search_selection_for_model_reset_keyboard_edit(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    dialog.show()
    _show_report_and_wait(qtbot, dialog, report)
    dialog.activateWindow()
    dialog.finding_search.setFocus()
    qtbot.waitUntil(dialog.finding_search.hasFocus)
    assert not dialog.browser.busy
    busy_hits: list[bool] = []
    states: list[tuple[bool, int, int, str, str]] = []

    def search_state() -> tuple[bool, int, int, str, str]:
        search = dialog.finding_search
        return (
            search.hasFocus(),
            search.cursorPosition(),
            search.selectionStart(),
            search.selectedText(),
            search.text(),
        )

    def on_busy(busy: bool) -> None:
        if not busy or busy_hits:
            return
        busy_hits.append(True)
        dialog.finding_search.setText("ShaXred")
        dialog.finding_search.setSelection(3, 1)
        states.append(search_state())

    def backspace_on_reset() -> None:
        states.append(search_state())
        qtbot.keyClick(dialog.finding_search, Qt.Key.Key_Backspace)
        states.append(search_state())

    dialog.browser.busy_changed.connect(on_busy)
    reset_hits = _observe_next_mod_model_reset(dialog, backspace_on_reset)
    dialog.reset_filters_button.click()
    _wait_for_view(qtbot, dialog)

    assert busy_hits == [True]
    assert reset_hits == [True]
    assert states == [
        (True, 4, 3, "X", "ShaXred"),
        (True, 4, 3, "X", "ShaXred"),
        (True, 3, -1, "", "Shared"),
    ]
    assert dialog.browser.filters == FindingFilters(
        frozenset({"error"}), query="Shared"
    )
    assert list(dialog.conflict_model.source_rows) == [1]
    assert dialog.report is report
    assert dialog.browser.conflicts is report["conflicts"]
    assert dialog.conflict_model.conflicts is report["conflicts"]
    assert (
        dialog.conflict_model.finding(dialog.conflict_model.index(0, 0))
        is report["conflicts"][1]
    )
    assert search_state() == (True, 3, -1, "", "Shared")


def test_prepared_reset_severity_is_projected_before_query(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    prepared_hits = 0
    prepared_state: dict[str, object] = {}
    publications: list[list[int]] = []

    force_one_row_per_tick(monkeypatch)
    dialog.browser.applied.connect(
        lambda view: publications.append(list(view.source_rows))
    )

    def request_query_during_prepared() -> None:
        nonlocal prepared_hits
        if prepared_hits:
            return
        prepared_hits += 1
        prepared_state.update(
            {
                "publications_before_query": list(publications),
                "browser_severities": dialog.browser.filters.severities,
                "checked_severities": _checked_severities(dialog),
            }
        )
        dialog.finding_search.setText("Shared")

    dialog.browser.prepared.connect(request_query_during_prepared)

    dialog.show_report(make_triage_report())
    dialog.reset_filters_button.click()
    _wait_for_view(qtbot, dialog)

    assert prepared_hits == 1
    assert prepared_state == {
        "publications_before_query": [],
        "browser_severities": frozenset({"error"}),
        "checked_severities": frozenset({"error"}),
    }
    assert dialog.browser.filters.severities == frozenset({"error"})
    assert dialog.browser.filters.query == "Shared"
    assert list(dialog.conflict_model.source_rows) == [1]


def test_model_reset_restores_source_selection_when_visible_index_changes(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    force_one_row_per_tick(monkeypatch)
    report = make_triage_report_with_moved_selection()

    dialog.show_report(report)
    _wait_for_view(qtbot, dialog)
    dialog.severity_buttons["all"].click()
    _wait_for_view(qtbot, dialog)

    assert list(dialog.conflict_model.source_rows) == [1, 3, 2, 4, 0, 5, 6]
    dialog.table.selectRow(3)
    assert dialog.table.currentIndex().row() == 3
    assert dialog.conflict_model.source_row(dialog.table.currentIndex()) == 4

    dialog.severity_buttons["error"].click()

    _wait_for_view(qtbot, dialog)
    assert list(dialog.conflict_model.source_rows) == [2, 4, 0, 5, 6]
    assert dialog.table.currentIndex().row() == 1
    assert dialog.conflict_model.source_row(dialog.table.currentIndex()) == 4
    assert dialog.conflict_model.source_row(dialog.conflict_model.index(3, 0)) == 5
    assert dialog.conflict_model.source_row(dialog.conflict_model.index(0, 0)) == 2
    assert (
        dialog.conflict_model.finding(dialog.table.currentIndex())
        is report["conflicts"][4]
    )


def test_result_feedback_uses_shown_and_total_lengths_without_iterating_rows(
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    dialog.show_report(report)
    dialog.browser.filters = dialog.browser.filters.__class__(frozenset({"error"}))
    dialog.conflict_model.set_rows(
        report["conflicts"],
        cast(Sequence[int], NonIterableSourceRows([1, 3])),
    )

    dialog._update_findings_feedback()

    assert dialog.result_label.text() == dialog.tr(
        "Showing {shown} of {total} findings."
    ).format(shown="2", total="4")


def test_severity_column_uses_interactive_width(
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, _, _ = dialog_setup
    header = dialog.table.horizontalHeader()

    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    assert dialog.table.columnWidth(0) > 0


def test_default_view_uses_finding_buckets_when_summary_counts_conflict(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup

    dialog.show_report(_conflicting_summary_report())

    _wait_for_view(qtbot, dialog)
    assert dialog.browser.filters.severities == frozenset({"error"})
    assert list(dialog.conflict_model.source_rows) == [1, 3]


def test_user_severity_choice_during_preparation_overrides_default_and_syncs_controls(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    _start_conflicting_report_preparation(dialog, monkeypatch)

    dialog.severity_buttons["all"].click()

    _wait_for_view(qtbot, dialog)
    assert dialog.browser.initial_filters.severities == frozenset({"error"})
    assert dialog.browser.filters.severities == frozenset({"error", "warning", "info"})
    assert list(dialog.conflict_model.source_rows) == [1, 3, 2, 0]
    assert dialog.severity_buttons["all"].isChecked()
    assert all(
        dialog.severity_buttons[name].isChecked()
        for name in ("error", "warning", "info")
    )


def test_mod_search_does_not_clear_hidden_active_filter(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    _show_report_and_wait(qtbot, dialog, make_triage_report())

    _select_mod_row(dialog, "example.b")
    _wait_for_view(qtbot, dialog)
    assert dialog.browser.filters.package_id == "example.b"
    assert list(dialog.conflict_model.source_rows) == [1]

    dialog.mod_search.setText("example.c")

    assert dialog.browser.filters.package_id == "example.b"
    assert list(dialog.conflict_model.source_rows) == [1]
    assert "example.b" in dialog.mod_filter_label.text().casefold()


def test_reset_during_preparation_uses_completed_default_severity(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    _start_conflicting_report_preparation(dialog, monkeypatch)

    dialog.reset_filters_button.click()

    _wait_for_view(qtbot, dialog)
    assert dialog.browser.initial_filters.severities == frozenset({"error"})
    assert dialog.browser.filters.severities == frozenset({"error"})
    assert list(dialog.conflict_model.source_rows) == [1, 3]
    assert dialog.browser.filters.package_id is None
    assert dialog.browser.filters.query == ""
    assert dialog.browser.filters.finding_type is None
    assert dialog.finding_search.text() == ""
    assert dialog.mod_search.text() == ""
    assert dialog.type_filter.currentData() is None


def test_reset_during_preparation_yields_to_later_explicit_all_query_and_type_request(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    _start_conflicting_report_preparation(dialog, monkeypatch)

    dialog.reset_filters_button.click()
    dialog.mod_search.setText("example.c")
    dialog.severity_buttons["all"].click()
    dialog.finding_search.setText("Shared")
    dialog.type_filter.setCurrentIndex(1)

    _wait_for_view(qtbot, dialog)
    _assert_shared_query_rows(
        dialog,
        finding_type="def",
        mod_search_text="example.c",
    )


def test_reset_during_preparation_yields_to_later_empty_severity_request(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    _start_conflicting_report_preparation(dialog, monkeypatch)

    dialog.reset_filters_button.click()
    for severity in ("error", "warning", "info"):
        dialog.severity_buttons[severity].click()

    _wait_for_view(qtbot, dialog)
    assert dialog.browser.filters.severities == frozenset()
    assert dialog.conflict_model.rowCount() == 0
    assert dialog.empty_label.text() == dialog.tr("Choose at least one severity.")


def test_reset_during_preparation_yields_to_later_query_only_request(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    _start_conflicting_report_preparation(dialog, monkeypatch)

    dialog.reset_filters_button.click()
    dialog.finding_search.setText("Shared")

    _wait_for_view(qtbot, dialog)
    _assert_shared_query_rows(dialog, finding_type=None)


def test_reset_restores_initial_severity(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    _show_report_and_wait(qtbot, dialog, _conflicting_summary_report())

    _filter_to_example_c_harmony_pawn(qtbot, dialog)
    assert list(dialog.conflict_model.source_rows) == [3]

    dialog.reset_filters_button.click()

    _wait_for_view(qtbot, dialog)
    assert dialog.browser.filters == dialog.browser.initial_filters
    assert dialog.browser.filters.severities == frozenset({"error"})
    assert dialog.browser.filters.package_id is None
    assert dialog.browser.filters.query == ""
    assert dialog.browser.filters.finding_type is None
    assert list(dialog.conflict_model.source_rows) == [1, 3]
    assert dialog.finding_search.text() == ""
    assert dialog.mod_search.text() == ""
    assert dialog.type_filter.currentData() is None


def test_duplicate_target_keeps_source_identity(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    _show_report_and_wait(qtbot, dialog, report)
    dialog.severity_buttons["all"].click()
    _wait_for_view(qtbot, dialog)

    dialog.table.selectRow(3)
    assert dialog.conflict_model.source_row(dialog.table.currentIndex()) == 0

    dialog.finding_search.setText("Shared")

    _wait_for_view(qtbot, dialog)
    assert list(dialog.conflict_model.source_rows) == [1, 0]
    assert dialog.table.currentIndex().row() == 1
    assert dialog.conflict_model.source_row(dialog.table.currentIndex()) == 0
    assert (
        dialog.conflict_model.finding(dialog.table.currentIndex())
        is report["conflicts"][0]
    )


def test_filtering_does_not_mark_stale_or_rescan(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, runner = dialog_setup
    report = make_triage_report()
    _show_report_and_wait(qtbot, dialog, report)
    summary_before = dialog.summary_label.text()

    _filter_to_example_c_harmony_pawn(qtbot, dialog)

    assert not dialog.is_stale
    assert runner.start_calls == 1
    assert runner.cancel_calls == 0
    assert dialog.summary_label.text() == summary_before
    assert list(dialog.conflict_model.source_rows) == [3]


def test_query_change_during_preparation_is_not_overwritten_by_default(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = dialog_setup[0]
    _start_conflicting_report_preparation(dialog, monkeypatch)
    all_severities = dialog.severity_buttons["all"]
    all_severities.click()
    dialog.finding_search.setText("Shared")
    dialog.type_filter.setCurrentIndex(1)

    _wait_for_view(qtbot, dialog)
    _assert_shared_query_rows(dialog, finding_type="def")


def test_preparation_yields_after_partial_progress_before_completion(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    force_one_row_per_tick(monkeypatch)
    partial_heartbeats = 0

    heartbeat = QTimer()

    def record_heartbeat() -> None:
        nonlocal partial_heartbeats
        traversed, total = _preparation_progress(dialog)
        if dialog.browser.busy and 0 < traversed < total:
            partial_heartbeats += 1

    heartbeat.timeout.connect(record_heartbeat)
    heartbeat.start(0)
    try:
        dialog.show_report(make_triage_report())
        _wait_for_view(qtbot, dialog)
    finally:
        heartbeat.stop()

    assert partial_heartbeats > 0


def test_filtering_yields_after_partial_progress_before_completion(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    force_one_row_per_tick(monkeypatch)
    _show_report_and_wait(qtbot, dialog, make_triage_report())
    partial_heartbeats = 0

    heartbeat = QTimer()

    def record_heartbeat() -> None:
        nonlocal partial_heartbeats
        traversed, total = _filter_progress(dialog)
        if dialog.browser.busy and 0 < traversed < total:
            partial_heartbeats += 1

    heartbeat.timeout.connect(record_heartbeat)
    heartbeat.start(0)
    try:
        dialog.severity_buttons["all"].click()
        _wait_for_view(qtbot, dialog)
    finally:
        heartbeat.stop()

    assert partial_heartbeats > 0


def test_latest_filter_generation_wins(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    force_one_row_per_tick(monkeypatch)
    _show_report_and_wait(qtbot, dialog, make_triage_report())
    first_rows = dialog.conflict_model.source_rows
    publications: list[list[int]] = []
    checkpoint: dict[str, int | bool | list[int]] | None = None
    shared_issued = False
    dialog.browser.applied.connect(
        lambda view: publications.append(list(view.source_rows))
    )

    original_continue_filtering = dialog.browser._continue_filtering
    dialog.browser._filter_timer.timeout.disconnect()

    dialog.severity_buttons["all"].click()
    old_request_generation = dialog.browser._filter_request_generation

    def observe_filter_tick() -> None:
        nonlocal checkpoint, shared_issued
        original_continue_filtering()
        traversed, total = _filter_progress(dialog)
        if checkpoint is not None:
            return
        if (
            dialog.browser.busy
            and 0 < traversed < total
            and dialog.browser._active_filter_request_generation
            == old_request_generation
            and dialog.browser._filter_request_generation == old_request_generation
        ):
            checkpoint = {
                "busy": dialog.browser.busy,
                "traversed": traversed,
                "total": total,
                "published_rows": list(dialog.conflict_model.source_rows),
                "active_rows": len(dialog.browser._active_filter_rows),
                "active_request": dialog.browser._active_filter_request_generation,
                "latest_request": dialog.browser._filter_request_generation,
            }
            print("SUPERSESSION_CHECKPOINT " + json.dumps(checkpoint))
            dialog.finding_search.setText("Shared")
            shared_issued = True

    dialog.browser._filter_timer.timeout.connect(observe_filter_tick)

    qtbot.waitUntil(lambda: shared_issued and checkpoint is not None)

    assert checkpoint == {
        "busy": True,
        "traversed": 1,
        "total": 4,
        "published_rows": [1, 3],
        "active_rows": 1,
        "active_request": old_request_generation,
        "latest_request": old_request_generation,
    }

    qtbot.wait(75)
    assert publications == []
    assert list(dialog.conflict_model.source_rows) == [1, 3]
    assert list(first_rows) == [1, 3]

    dialog.finding_search.setText("Pawn")
    _wait_for_view(qtbot, dialog)

    assert publications == [[3]]
    assert list(dialog.conflict_model.source_rows) == [3]
    assert list(first_rows) == [1, 3]


def test_close_invalidates_filtering(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, _ = dialog_setup
    force_one_row_per_tick(monkeypatch)
    _show_report_and_wait(qtbot, dialog, make_triage_report())
    publications: list[list[int]] = []
    dialog.browser.applied.connect(
        lambda view: publications.append(list(view.source_rows))
    )

    dialog.severity_buttons["all"].click()
    assert dialog.browser.busy
    dialog.close()
    _process_next_event_turn(qtbot)

    assert publications == []
    assert not dialog.browser.busy
    assert list(dialog.conflict_model.source_rows) == [1, 3]


@pytest.mark.parametrize(
    "million_rows",
    [
        False,
        pytest.param(
            True,
            marks=pytest.mark.skipif(
                os.environ.get("RIMSORT_RCD_UI_LARGE_SMOKE") != "1",
                reason="set RIMSORT_RCD_UI_LARGE_SMOKE=1 for the million-row smoke",
            ),
        ),
    ],
)
def test_large_report_is_cooperative(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    million_rows: bool,
) -> None:
    dialog, _, _ = dialog_setup
    reference_count = 1_000_000 if million_rows else 10_000
    report = make_large_triage_report(reference_count)

    prep_partial_heartbeats = 0
    prep_timer = QTimer()

    def record_preparation_heartbeat() -> None:
        nonlocal prep_partial_heartbeats
        traversed, total = _preparation_progress(dialog)
        if dialog.browser.busy and 0 < traversed < total:
            prep_partial_heartbeats += 1

    prep_timer.timeout.connect(record_preparation_heartbeat)
    prep_timer.start(0)
    prep_started = time.monotonic()
    dialog.show_report(report)
    _wait_for_view(qtbot, dialog)
    prep_elapsed = time.monotonic() - prep_started
    prep_timer.stop()

    assert dialog.conflict_model.rowCount() == reference_count // 2
    assert dialog.conflict_model.source_row(dialog.conflict_model.index(0, 0)) == 1

    dialog.severity_buttons["all"].click()
    _wait_for_view(qtbot, dialog)
    assert dialog.conflict_model.rowCount() == reference_count

    _select_mod_row(dialog, "example.c")
    _wait_for_view(qtbot, dialog)
    filter_partial_heartbeats = 0
    filter_timer = QTimer()

    def record_filter_heartbeat() -> None:
        nonlocal filter_partial_heartbeats
        traversed, total = _filter_progress(dialog)
        if dialog.browser.busy and 0 < traversed < total:
            filter_partial_heartbeats += 1

    filter_timer.timeout.connect(record_filter_heartbeat)
    filter_timer.start(0)
    filter_started = time.monotonic()
    dialog.finding_search.setText("Pawn")
    _wait_for_view(qtbot, dialog)
    filter_elapsed = time.monotonic() - filter_started
    filter_timer.stop()

    assert dialog.conflict_model.rowCount() == reference_count // 4
    assert dialog.conflict_model.source_row(dialog.conflict_model.index(0, 0)) == 3
    print(
        "large-report-ui-smoke "
        f"references={reference_count} prep_seconds={prep_elapsed:.3f} "
        f"prep_partial_heartbeats={prep_partial_heartbeats} "
        f"filter_seconds={filter_elapsed:.3f} "
        f"filter_partial_heartbeats={filter_partial_heartbeats}"
    )
    if million_rows:
        assert prep_partial_heartbeats > 0
        assert filter_partial_heartbeats > 0


def test_blank_mod_name_uses_package_id_in_sidebar(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    report["conflicts"][0]["mods"][0]["name"] = ""
    report["conflicts"][1]["mods"][0]["name"] = ""
    report["conflicts"][3]["patches"][0]["mod_summary"]["name"] = ""
    report["conflicts"][3]["patches"][1]["mod_summary"]["name"] = ""
    _show_report_and_wait(qtbot, dialog, report)

    assert dialog.mod_model.index(1, 0).data() == "example.a"
    dialog.mod_search.setText("example.a")
    _select_mod_row(dialog, "example.a")
    _wait_for_view(qtbot, dialog)
    assert dialog.browser.filters.package_id == "example.a"
    assert "example.a" in dialog.mod_filter_label.text()


def test_mod_sidebar_search_matches_unicode_plain_text_names(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = make_triage_report()
    report["conflicts"][0]["mods"][0]["name"] = "Mód <猫>"
    report["conflicts"][1]["mods"][0]["name"] = "Mód <猫>"
    report["conflicts"][3]["patches"][0]["mod_summary"]["name"] = "Mód <猫>"
    report["conflicts"][3]["patches"][1]["mod_summary"]["name"] = "Mód <猫>"
    _show_report_and_wait(qtbot, dialog, report)

    assert dialog.mod_model.index(1, 0).data() == "Mód <猫>"
    dialog.mod_search.setText("mód <猫>")
    _select_mod_row(dialog, "example.a")
    _wait_for_view(qtbot, dialog)
    assert dialog.browser.filters.package_id == "example.a"
    assert dialog.mod_model.rowCount() == 2


def test_accept_during_preparation_disposes_without_late_publication(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog, _, runner = dialog_setup
    force_one_row_per_tick(monkeypatch)
    publications: list[list[int]] = []
    dialog.browser.applied.connect(
        lambda view: publications.append(list(view.source_rows))
    )

    dialog.show_report(_conflicting_summary_report())
    dialog.reset_filters_button.click()

    dialog.accept()
    _process_next_event_turn(qtbot)

    assert not dialog.isVisible()
    assert publications == []
    assert not dialog.browser.busy
    assert runner.cancel_calls == 0


def test_done_cancels_active_scan_once_and_disposes_browser(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, runner = dialog_setup

    dialog.done(int(QDialog.DialogCode.Accepted))
    _process_next_event_turn(qtbot)

    assert runner.cancel_calls == 1
    assert dialog.state == "cancelled"
    assert runner.request is not None
    runner.succeeded.emit(runner.request["id"], make_report("error", False))
    assert dialog.report == {}
    dialog.close()
    assert runner.cancel_calls == 1


@pytest.mark.parametrize("focus_target", ["close", "notes"])
def test_completed_update_preserves_user_focus(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    monkeypatch: pytest.MonkeyPatch,
    focus_target: str,
) -> None:
    dialog, _, _ = dialog_setup
    force_one_row_per_tick(monkeypatch)
    dialog.show()
    dialog.show_report(make_triage_report())
    _wait_for_view(qtbot, dialog)

    dialog.severity_buttons["all"].click()
    assert dialog.browser.busy

    if focus_target == "close":
        target = _close_button(dialog)
        target.setFocus(Qt.FocusReason.TabFocusReason)
    else:
        dialog.tabs.setCurrentIndex(1)
        dialog.notes.details_view.setFocus(Qt.FocusReason.TabFocusReason)
        target = dialog.notes.details_view

    assert dialog.focusWidget() is target
    _wait_for_view(qtbot, dialog)
    assert dialog.focusWidget() is target


def test_initial_size_clamps_to_primary_screen_fallback(
    dialog_setup: tuple[Any, Any, FakeRunner], monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog, _, _ = dialog_setup
    available = FakeScreen(QRect(0, 0, 820, 560))
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: available)
    monkeypatch.setattr(dialog, "screen", lambda: None)

    dialog._resize_for_screen()

    _assert_dialog_fits_screen(dialog, 820, 560)


def test_initial_size_prefers_dialog_screen_over_larger_primary_screen(
    dialog_setup: tuple[Any, Any, FakeRunner], monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog, _, _ = dialog_setup
    secondary = FakeScreen(QRect(0, 0, 820, 560))
    monkeypatch.setattr(
        QApplication,
        "primaryScreen",
        lambda: FakeScreen(QRect(0, 0, 2400, 1600)),
    )
    monkeypatch.setattr(dialog, "screen", lambda: secondary)

    dialog._resize_for_screen()

    _assert_dialog_fits_screen(dialog, 820, 560)


@pytest.mark.parametrize(("width", "height"), [(1280, 900), (1440, 1000)])
def test_findings_workspace_keeps_header_compact_after_resize(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    width: int,
    height: int,
) -> None:
    dialog, _, _ = dialog_setup
    dialog.show()
    dialog.resize(width, height)
    dialog.show_report(make_triage_report())
    _wait_for_view(qtbot, dialog)
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    qtbot.wait(20)
    splitter = dialog.findChild(QSplitter)
    assert splitter is not None
    findings_tab = dialog.tabs.widget(0)
    compact_summary_limit = dialog.summary_label.sizeHint().height() * 2
    usable_workspace_height = findings_tab.contentsRect().height()

    assert dialog.summary_label.height() <= compact_summary_limit
    assert splitter.height() >= int(usable_workspace_height * 0.6)


def test_report_shows_native_mod_counts_distinct_from_snapshot(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report = make_report("error", False)
    report["summary"]["total_mods"] = 17
    report["summary"]["mods_with_conflicts"] = 9
    dialog.show_report(report)
    _wait_for_view(qtbot, dialog)
    assert "17" in dialog.summary_label.text()
    assert "9" in dialog.summary_label.text()
    assert "2" in dialog.instance_label.text()


def test_report_renders_severity_and_incomplete_separately(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    dialog.show_report(make_report(severity="error", diagnostic_incomplete=True))
    _wait_for_view(qtbot, dialog)
    assert dialog.conflict_model.index(0, 0).data() == "Error"
    assert (
        dialog.conflict_model.index(0, 1).data() == "ThingDef: A — Direct replacement"
    )
    assert dialog.instance_label.text() == dialog.tr(
        "Instance: {instance}; usable mods: {count}"
    ).format(instance="instance-a", count=2)
    assert dialog.summary_label.text() == (
        "Parsed mods: 1; Mods with conflicts: 1; Errors: 1; Warnings: 0; Info: 0"
    )
    assert dialog.is_incomplete
    assert not dialog.is_stale


def test_active_list_change_latches_stale_after_result(
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, widget, runner = dialog_setup
    widget.insertItem(0, widget.takeItem(1))
    assert dialog.is_stale
    assert runner.request is not None
    runner.succeeded.emit(runner.request["id"], make_report("error", False))
    assert dialog.state == "finished"
    assert dialog.is_stale


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize(
    "event", ["insert", "remove", "move", "reset", "layout", "data", "instance"]
)
def test_changes_latch_stale(
    dialog_setup: tuple[Any, Any, FakeRunner], completed: bool, event: str
) -> None:
    dialog, widget, runner = dialog_setup
    assert runner.request is not None
    if completed:
        runner.succeeded.emit(runner.request["id"], make_report("error", False))
    model = widget.model()
    if event == "insert":
        widget.addItem("new")
    elif event == "remove":
        widget.takeItem(0)
    elif event == "move":
        parent = model.index(-1, -1)
        model.rowsMoved.emit(parent, 0, 0, parent, 2)
    elif event == "reset":
        model.modelReset.emit()
    elif event == "layout":
        model.layoutChanged.emit()
    elif event == "data":
        index = model.index(0, 0)
        model.dataChanged.emit(index, index, [])
    else:
        EventBus().do_activate_current_instance.emit("instance-a")
    assert dialog.is_stale
    if not completed:
        runner.succeeded.emit(runner.request["id"], make_report("error", False))
        assert dialog.is_stale


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize(
    "change",
    ["refresh_start", "refresh_end", "refresh_end_only", "version", "metadata"],
)
def test_metadata_changes_invalidate_snapshot(
    dialog_setup: tuple[Any, Any, FakeRunner], completed: bool, change: str
) -> None:
    dialog, widget, runner = dialog_setup
    assert runner.request is not None
    if completed:
        runner.succeeded.emit(runner.request["id"], make_report("error", False))
    metadata = widget.metadata_controller
    if change == "refresh_start":
        metadata.metadata_refresh_started.emit()
    elif change == "refresh_end":
        metadata.metadata_refresh_started.emit()
        metadata.metadata_refreshed.emit()
    elif change == "refresh_end_only":
        metadata.metadata_refreshed.emit()
    elif change == "version":
        metadata.game_version = "1.8"
        metadata.metadata_refreshed.emit()
    else:
        metadata.mod_metadata_updated_signal.emit("path")
    assert dialog.is_stale
    if not completed:
        runner.succeeded.emit(runner.request["id"], make_report("error", False))
        assert dialog.is_stale


@pytest.mark.parametrize("completed", [False, True])
def test_unchanged_metadata_refresh_shows_uncertain_stale_status(
    dialog_setup: tuple[Any, Any, FakeRunner], completed: bool
) -> None:
    dialog, widget, runner = dialog_setup
    metadata = widget.metadata_controller
    before = snapshot_active_mods(widget, metadata, "instance-a")
    assert before == dialog.snapshot
    assert runner.request is not None
    if completed:
        runner.succeeded.emit(runner.request["id"], make_report("error", False))

    metadata.metadata_refreshed.emit()
    assert snapshot_active_mods(widget, metadata, "instance-a") == before
    assert dialog.is_stale
    assert dialog.status_label.text().endswith(
        "Stale: the active snapshot may have changed"
    )

    if not completed:
        runner.succeeded.emit(runner.request["id"], make_report("error", False))
        assert dialog.state == "finished"
        assert dialog.status_label.text().endswith(
            "Stale: the active snapshot may have changed"
        )


def test_result_rechecks_version_without_signal(
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, widget, runner = dialog_setup
    widget.metadata_controller.game_version = "1.8"
    assert runner.request is not None
    runner.succeeded.emit(runner.request["id"], make_report("error", False))
    assert dialog.state == "finished"
    assert dialog.is_stale


def test_no_input_never_starts_worker(qtbot: Any, tmp_path: Path) -> None:
    widget, _, _ = make_two_mod_list(qtbot, tmp_path)
    widget.clear()
    runner = FakeRunner()
    snapshot = snapshot_active_mods(widget, widget.metadata_controller, "instance-a")
    dialog = ConflictReportDialog(
        widget, widget.metadata_controller, lambda: "instance-a", snapshot, runner
    )
    qtbot.addWidget(dialog)
    dialog.show()
    assert runner.request is None
    assert dialog.state == "no_input"
    assert dialog.tr("No usable mod inputs") in dialog.status_label.text()
    assert not dialog.result_label.isVisible()
    assert not dialog.empty_label.isVisible()
    assert not dialog.is_incomplete
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    assert dialog.notes.model.rowCount() == 0


def test_no_input_and_cancellation_preserve_snapshot_notes(
    qtbot: Any, tmp_path: Path
) -> None:
    from app.services.conflict_snapshot import InputIssue, ScanSnapshot

    widget, _, _ = make_two_mod_list(qtbot, tmp_path)
    issue = InputIssue("unusable", "/full/mod/path")
    for paths in ((), ("/usable/mod",)):
        runner = FakeRunner()
        snapshot = ScanSnapshot(paths, None, "instance", (issue,))
        dialog = ConflictReportDialog(
            widget, widget.metadata_controller, lambda: "instance", snapshot, runner
        )
        qtbot.addWidget(dialog)
        if paths:
            dialog.cancel_scan()
            assert dialog.state == "cancelled"
            assert runner.cancel_calls == 1
        else:
            assert dialog.state == "no_input"
            assert runner.start_calls == 0
        _select_note(qtbot, dialog, "input")
        assert "unusable: /full/mod/path" in dialog.notes.details_view.toPlainText()
        _select_note(qtbot, dialog, "version")
        assert "Unknown game version" in dialog.notes.details_view.toPlainText()
        assert dialog.notes.model.attention_count == 2


def test_failure_and_cancel_ignore_late_success(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
) -> None:
    dialog, _, runner = dialog_setup
    dialog.show()
    assert runner.request is not None
    runner.failed.emit(runner.request["id"], "failure text")
    assert dialog.state == "failed"
    assert not dialog.result_label.isVisible()
    assert not dialog.empty_label.isVisible()
    _select_note(qtbot, dialog, "failure")
    assert "failure text" in dialog.notes.details_view.toPlainText()
    runner.succeeded.emit(runner.request["id"], make_report("error", False))
    assert dialog.state == "failed"
    assert not dialog.result_label.isVisible()
    assert not dialog.empty_label.isVisible()


@pytest.mark.parametrize("outcome", ["failed", "cancelled"])
def test_unavailable_scan_has_no_zero_result_feedback(
    dialog_setup: tuple[Any, Any, FakeRunner], outcome: str
) -> None:
    dialog, _, runner = dialog_setup
    dialog.show()
    assert runner.request is not None
    assert dialog.tr("Scanning…") in dialog.status_label.text()
    assert not dialog.result_label.isVisible()
    assert not dialog.empty_label.isVisible()
    if outcome == "failed":
        runner.failed.emit(runner.request["id"], "failure")
        assert dialog.tr("Scan failed") in dialog.status_label.text()
    else:
        dialog.cancel_scan()
        assert dialog.tr("Scan cancelled") in dialog.status_label.text()
        assert not dialog.result_label.isVisible()
        assert not dialog.empty_label.isVisible()
        runner.cancelled.emit(runner.request["id"])
        runner.succeeded.emit(runner.request["id"], make_report("error", False))
        assert dialog.state == "cancelled"
        assert dialog.tr("Scan cancelled") in dialog.status_label.text()
    assert not dialog.result_label.isVisible()
    assert not dialog.empty_label.isVisible()


def test_successful_empty_report_keeps_zero_result_feedback(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, runner = dialog_setup
    dialog.show()
    assert runner.request is not None
    report = make_report("warning", False)
    report["conflicts"] = []
    runner.succeeded.emit(runner.request["id"], report)
    _wait_for_view(qtbot, dialog)
    assert dialog.result_label.isVisible()
    assert dialog.result_label.text() == dialog.tr(
        "Showing {shown} of {total} findings."
    ).format(shown=0, total=0)
    assert dialog.empty_label.isVisible()
    assert dialog.empty_label.text() == dialog.tr("No findings reported.")


def test_native_diagnostic_translation_and_fallback(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner], tmp_path: Path
) -> None:
    dialog, _, _ = dialog_setup
    app, translator = _install_translator(
        tmp_path,
        "diagnostics",
        '<TS version="2.1" language="fr"><context>'
        "<name>ConflictDetectorDiagnostic</name><message>"
        "<source>Failed to parse mod at {path}: {detail}</source>"
        "<translation>Échec pour {path} : {detail}</translation>"
        "</message></context></TS>",
    )
    try:
        report: dict[str, Any] = make_report("warning", True)
        diagnostic = report["diagnostics"][0]
        diagnostic.update(
            code="about_parse_failure",
            params={"path": "/tmp/<mod>", "detail": "bad"},
            message="raw message",
        )
        dialog.show_report(report)
        _select_note(qtbot, dialog, "native")
        assert "Échec pour /tmp/<mod> : bad" in dialog.notes.details_view.toPlainText()
        diagnostic["params"] = {"path": "invalid-\udcff", "detail": "bad"}
        dialog.show_report(report)
        _select_note(qtbot, dialog, "native")
        assert (
            "Échec pour invalid-\\udcff : bad"
            in dialog.notes.details_view.toPlainText()
        )
        diagnostic["params"] = {}
        dialog.show_report(report)
        _select_note(qtbot, dialog, "native")
        assert "raw message" in dialog.notes.details_view.toPlainText()
        diagnostic["code"] = "unknown_future_code"
        dialog.show_report(report)
        _select_note(qtbot, dialog, "native")
        assert "raw message" in dialog.notes.details_view.toPlainText()
        del diagnostic["code"]
        dialog.show_report(report)
        _select_note(qtbot, dialog, "native")
        assert "raw message" in dialog.notes.details_view.toPlainText()
    finally:
        app.removeTranslator(translator)


def test_inspector_labels_translate_from_real_catalog(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    tmp_path: Path,
) -> None:
    dialog, _, _ = dialog_setup
    app, translator = _install_translator(
        tmp_path,
        "inspector",
        '<TS version="2.1" language="fr"><context><name>ConflictReportDialog</name>'
        "<message><source>Winner</source><translation>Gagnant</translation></message>"
        "<message><source>Condition</source><translation>Condition traduite</translation></message>"
        "<message><source>Author</source><translation>Auteur traduit</translation></message>"
        "<message><source>Show raw finding data</source><translation>Afficher les données brutes</translation></message>"
        "</context></TS>",
    )
    try:
        report = make_triage_report()
        _show_report_and_wait(qtbot, dialog, report)
        assert "Gagnant" in dialog.inspector.outcome_label.text()
        assert "Condition traduite" in dialog.inspector.outcome_label.text()
        assert dialog.inspector.raw_button.text() == "Afficher les données brutes"
        dialog.inspector.technical_button.click()
        assert "Auteur traduit" in _inspector_text(dialog)
    finally:
        app.removeTranslator(translator)


def test_native_diagnostic_worker_to_dialog(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner], tmp_path: Path
) -> None:
    import json

    from tests.services.test_conflict_detector_worker import run_guarded_entrypoint

    library = os.environ.get("RIMSORT_RCD_LIBRARY")
    if not library or not Path(library).is_file():
        pytest.skip("set RIMSORT_RCD_LIBRARY to the authorized debug library")
    missing = tmp_path / "missing mod"
    result = run_guarded_entrypoint(
        tmp_path,
        library,
        {
            "protocol": 1,
            "id": "diagnostic",
            "config": {"mod_paths": [str(missing)], "ordered": True},
        },
    )
    assert result.returncode == 0, result.stderr
    frames = [json.loads(line) for line in result.stdout.splitlines()]
    report = frames[-1]["report"]
    diagnostic = report["diagnostics"][0]
    assert diagnostic["code"] == "about_parse_failure"
    assert diagnostic["params"]["path"] == str(missing)
    dialog, _, _ = dialog_setup
    dialog.show_report(report)
    _select_note(qtbot, dialog, "native")
    details = dialog.notes.details_view.toPlainText()
    assert f"Failed to parse mod at {missing}:" in details
    assert diagnostic["params"]["detail"] in details


def test_details_and_ordinary_diagnostics(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report: dict[str, Any] = make_report("warning", False)
    report["diagnostics"][0]["severity"] = "error"
    report["diagnostics"][0]["message"] = "load order violation"
    report["conflicts"][0]["winner"] = "example.a"
    dialog.show_report(report)
    _wait_for_view(qtbot, dialog)
    dialog.table.selectRow(0)
    details = _inspector_text(dialog)
    assert "example.a" in details
    assert "ThingDef" in details
    _select_note(qtbot, dialog, "native")
    assert "load order violation" in dialog.notes.details_view.toPlainText()
    assert not dialog.is_incomplete


@pytest.fixture
def harmony_report() -> dict[str, Any]:
    report: dict[str, Any] = make_report("error", False)
    mod = report["conflicts"][0]["mods"][0]
    report["conflicts"] = [
        {
            "type": "harmony",
            "severity": "error",
            "target": {
                "type_name": "Verse.Pawn",
                "method_name": "Tick",
                "parameter_types": [],
            },
            "patches": [
                {
                    "mod_summary": mod,
                    "dll_name": "mod.dll",
                    "patch_kind": "prefix",
                    "priority": 0,
                    "before": [],
                    "after": [],
                    "returns_bool": True,
                }
            ],
            "short_circuit_risk": True,
            "execution_order": None,
        }
    ]
    return report


def test_harmony_target_and_patch_details(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    harmony_report: dict[str, Any],
) -> None:
    dialog, _, _ = dialog_setup
    dialog.show_report(harmony_report)
    _wait_for_view(qtbot, dialog)
    assert dialog.conflict_model.index(0, 1).data() == "Verse.Pawn.Tick — Harmony"
    assert dialog.conflict_model.index(0, 2).data() == "A"
    dialog.table.selectRow(0)
    dialog.inspector.technical_button.click()
    details = _inspector_text(dialog)
    assert "mod.dll" in details
    assert "prefix" in details


@pytest.mark.parametrize(
    "mechanism, expected_labels, expected_values",
    [
        (
            {"direct_replacement": {"divergent_fields": ["label", "description"]}},
            ["Direct replacement", "Divergent fields"],
            ["label", "description"],
        ),
        (
            {
                "x_path_overlap": {
                    "xpath_a": "/Defs/猫",
                    "xpath_b": "/Defs/*",
                    "wildcard": True,
                }
            },
            ["XPath overlap", "First XPath", "Second XPath", "Wildcard"],
            ["/Defs/猫", "/Defs/*"],
        ),
        (
            {
                "x_path_on_replaced_def": {
                    "xpath": "/Defs/Thing",
                    "replaced_by": "mód.b",
                }
            },
            ["XPath on replaced Def", "XPath", "Replaced by"],
            ["/Defs/Thing", "mód.b"],
        ),
        (
            {"xpath_same_def_non_overlap": {"xpath_pairs": [["/A", "/B"]]}},
            ["Non-overlapping XPath edits", "XPath pairs"],
            ["/A", "/B"],
        ),
    ],
)
def test_def_details_use_translatable_labels_and_preserve_values(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    mechanism: dict[str, Any],
    expected_labels: list[str],
    expected_values: list[str],
) -> None:
    dialog, _, _ = dialog_setup
    report: dict[str, Any] = make_report("warning", False)
    finding = report["conflicts"][0]
    finding["target"] = {"def_type": "ThingDéf", "def_name": "猫"}
    finding["mods"][0]["name"] = "Mód"
    finding["mods"][0]["package_id"] = "mód.a"
    finding["winner"] = "mód.a"
    finding["condition"] = "path-\udcff"
    finding["mechanism"] = mechanism
    dialog.show_report(report)
    _wait_for_view(qtbot, dialog)
    dialog.table.selectRow(0)
    dialog.inspector.technical_button.click()
    details = _inspector_text(dialog)
    for label in [
        "Def type",
        "Def name",
        "Mods",
        "Winner",
        "Condition",
        "Mechanism",
        *expected_labels,
    ]:
        assert dialog.tr(label) in details
    for value in ["ThingDéf", "猫", "Mód", "mód.a", "path-\\udcff", *expected_values]:
        assert value in details
    assert "\\u732b" not in details


def test_harmony_details_use_translatable_labels_and_preserve_values(
    qtbot: Any,
    dialog_setup: tuple[Any, Any, FakeRunner],
    harmony_report: dict[str, Any],
) -> None:
    dialog, _, _ = dialog_setup
    conflict = harmony_report["conflicts"][0]
    conflict["patches"][0]["mod_summary"]["name"] = "Mód 猫"
    conflict["patches"][0]["mod_summary"]["author"] = "<author 猫>-\udcff"
    conflict["patches"].append(
        {
            "mod_summary": {
                "package_id": "example.a",
                "name": "Mód 猫",
                "author": None,
                "is_base_content": False,
            },
            "dll_name": "mód-extra.dll",
            "patch_kind": "postfix",
            "priority": 300,
            "before": ["before.extra"],
            "after": ["after.extra"],
            "returns_bool": False,
        }
    )
    conflict["target"]["parameter_types"] = ["猫"]
    conflict["patches"][0].update(
        dll_name="mód.dll", priority=400, before=["before.id"], after=["after.id"]
    )
    conflict["execution_order"] = ["example.a"]
    dialog.show_report(harmony_report)
    _wait_for_view(qtbot, dialog)
    dialog.table.selectRow(0)
    dialog.inspector.technical_button.click()
    details = _inspector_text(dialog)
    for label in [
        "Type",
        "Method",
        "Parameter types",
        "Patches",
        "Mod",
        "Name",
        "Package ID",
        "Author",
        "Base content",
        "DLL",
        "Patch kind",
        "Priority",
        "Before",
        "After",
        "Returns bool",
        "Short-circuit risk",
        "Execution order",
    ]:
        assert dialog.tr(label) in details
    for value in [
        "Verse.Pawn",
        "Tick",
        "猫",
        "Mód 猫",
        "<author 猫>-\\udcff",
        "mód.dll",
        "mód-extra.dll",
        "prefix",
        "postfix",
        "400",
        "300",
        "before.id",
        "after.id",
        "before.extra",
        "after.extra",
        "example.a",
    ]:
        assert value in details
    assert "\\u732b" not in details


def test_details_show_unicode_and_escape_surrogate_safely(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report: dict[str, Any] = make_report("error", False)
    report["conflicts"][0]["target"]["def_name"] = "猫"
    report["conflicts"][0]["condition"] = "path-\udcff"
    dialog.show_report(report)
    _wait_for_view(qtbot, dialog)
    dialog.table.selectRow(0)
    details = _inspector_text(dialog)
    assert "猫" in details
    assert "\\u732b" not in details
    assert "path-\\udcff" in details


def test_detail_labels_are_extracted_for_translation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    messages = extract_context_sources(
        tmp_path,
        [
            root / "app/windows/conflict_report_dialog.py",
            root / "app/views/conflict_report_details.py",
            root / "app/models/conflict_report.py",
        ],
        "detail-labels.ts",
        "ConflictReportDialog",
    )
    expected = {
        "Technical details",
        "After",
        "Author",
        "Base content",
        "Before",
        "Condition",
        "DLL",
        "Def name",
        "Def type",
        "Execution order",
        "Explanation",
        "Mechanism",
        "Method",
        "Mod",
        "Mods",
        "Name",
        "Package ID",
        "Parameter types",
        "Participant mods",
        "Patch kind",
        "Patches",
        "Priority",
        "Preparing scan notes (…)",
        "Raw finding data",
        "Reported outcome",
        "Returns bool",
        "Scan notes: {count}",
        "Severity",
        "Short-circuit risk",
        "Show raw finding data",
        "Hide raw finding data",
        "Target",
        "Type",
        "Winner",
        "Direct replacement",
        "Divergent fields",
        "XPath overlap",
        "First XPath",
        "Second XPath",
        "Wildcard",
        "XPath on replaced Def",
        "XPath",
        "Replaced by",
        "Non-overlapping XPath edits",
        "XPath pairs",
        "Unknown game version: version-specific content may have been skipped.",
        "This report says one mod directly replaced another definition. Replacements may be intentional and are not proof of broken gameplay.",
        "These mods edit overlapping XPath targets on the same definition. Overlap may be intentional and is not proof of broken gameplay.",
        "This mod edits a definition that another mod replaced. That relationship may be intentional and is not proof of broken gameplay.",
        "These mods edit different XPath targets on the same definition. Shared targets may be intentional and are not proof of broken gameplay.",
        "These Harmony patches target the same method. Patch overlap may be intentional and is not proof of broken gameplay.",
        "Harmony patches do not report a Def-style winner.",
    }
    assert expected <= messages, expected - messages

    note_messages = extract_context_sources(
        tmp_path,
        root / "app/views/conflict_report_details.py",
        "note-detail-labels.ts",
        "ScanNotesView",
    )
    note_expected = {"Path", "Show raw note data"}
    assert note_expected <= note_messages, note_expected - note_messages


def test_empty_best_effort_report(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner]
) -> None:
    dialog, _, _ = dialog_setup
    report: dict[str, Any] = make_report("error", False)
    report["conflicts"] = []
    report["summary"]["conflicts_by_severity"] = {"error": 0, "warning": 0, "info": 0}
    dialog.show_report(report)
    _wait_for_view(qtbot, dialog)
    assert dialog.conflict_model.rowCount() == 0
    assert dialog.empty_label.text() == dialog.tr("No findings reported.")
    assert not dialog.is_incomplete
    assert "Best effort" in dialog.context_label.text()


@pytest.mark.skipif(os.name == "nt", reason="surrogate-escaped paths are Unix-specific")
def test_surrogate_row_issue_is_visible_safely(qtbot: Any, tmp_path: Path) -> None:
    bad = tmp_path / os.fsdecode(b"invalid-\xff")
    bad.mkdir()
    key = str(bad)
    good = tmp_path / "good"
    good.mkdir()
    mods = {
        key: AboutXmlMod(name="Bad", _mod_path=bad),
        str(good): AboutXmlMod(name="Good", _mod_path=good),
    }
    widget = _make_active_mod_list(qtbot, mods, list(mods))
    controller = cast(MagicMock, widget.metadata_controller)
    controller.get_mod.side_effect = mods.get
    controller.game_version = "Unknown"
    snapshot = snapshot_active_mods(widget, controller, "instance-a")
    assert snapshot.issues[0].path == key
    runner = FakeRunner()
    dialog = ConflictReportDialog(
        widget, controller, lambda: "instance-a", snapshot, runner
    )
    qtbot.addWidget(dialog)
    assert runner.request is not None
    assert dialog.is_incomplete
    _select_note(qtbot, dialog, "input")
    assert "invalid-\\udcff" in dialog.notes.details_view.toPlainText()
    assert "Unknown" in dialog.version_label.text()


@pytest.mark.parametrize("dismissal", ["escape", "reject", "close_button", "close"])
def test_dismissal_cancels_only_own_worker_and_ignores_late_signals(
    qtbot: Any, dialog_setup: tuple[Any, Any, FakeRunner], dismissal: str
) -> None:
    dialog, widget, runner = dialog_setup
    other_runner = FakeRunner()
    other = ConflictReportDialog(
        widget,
        widget.metadata_controller,
        lambda: "instance-a",
        dialog.snapshot,
        other_runner,
    )
    qtbot.addWidget(other)
    dialog.show()
    if dismissal == "escape":
        qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    elif dismissal == "reject":
        dialog.reject()
    elif dismissal == "close_button":
        next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == dialog.tr("Close")
        ).click()
    else:
        dialog.close()
    assert not dialog.isVisible()
    assert runner.cancel_called
    assert not other_runner.cancel_called
    assert dialog.state == "cancelled"
    assert runner.request is not None
    runner.progress.emit(runner.request["id"], 1, 2, "late")
    runner.failed.emit(runner.request["id"], "late")
    runner.succeeded.emit(runner.request["id"], make_report("error", False))
    assert dialog.state == "cancelled"
    assert dialog.report == {}


def test_cancel_requests_termination(dialog_setup: tuple[Any, Any, FakeRunner]) -> None:
    dialog, _, runner = dialog_setup
    dialog.close()
    assert runner.cancel_called
    assert runner.request is not None
    runner.succeeded.emit(runner.request["id"], make_report("error", False))
    assert dialog.state == "cancelled"
