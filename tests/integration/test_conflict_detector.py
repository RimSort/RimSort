"""Source-mode integration through the real menu and native worker."""

import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QLabel, QMenuBar
from shiboken6 import isValid

from app.controllers.menu_bar_controller import MenuBarController
from app.services.conflict_detector_runner import ConflictDetectorRunner
from app.views.main_content_panel import MainContent
from app.views.menu_bar import MenuBar
from tests.views.test_mods_panel import make_two_mod_list


def integration_prerequisite() -> str | None:
    library = os.environ.get("RIMSORT_RCD_LIBRARY", "")
    if os.environ.get("RIMSORT_DEV") != "1":
        return "set RIMSORT_DEV=1 for source-mode integration"
    if not library or not Path(library).is_absolute() or not Path(library).is_file():
        return "set RIMSORT_RCD_LIBRARY to an absolute existing debug library"
    try:
        ctypes.CDLL(library)
    except OSError as exc:
        return f"native debug library cannot be loaded: {exc}"
    return None


def enforce_integration_prerequisite() -> None:
    reason = integration_prerequisite()
    if reason:
        if os.environ.get("RIMSORT_REQUIRE_RCD_INTEGRATION") == "1":
            pytest.fail(reason)
        pytest.skip(reason)


@pytest.fixture
def require_integration() -> None:
    enforce_integration_prerequisite()


def test_integration_prerequisite_reports_missing_library(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RIMSORT_DEV", "1")
    monkeypatch.delenv("RIMSORT_RCD_LIBRARY", raising=False)
    assert "RIMSORT_RCD_LIBRARY" in (integration_prerequisite() or "")


@pytest.mark.parametrize("required", [False, True])
def test_missing_prerequisite_skip_or_fail(
    monkeypatch: pytest.MonkeyPatch, required: bool
) -> None:
    monkeypatch.setenv("RIMSORT_DEV", "1")
    monkeypatch.delenv("RIMSORT_RCD_LIBRARY", raising=False)
    if required:
        monkeypatch.setenv("RIMSORT_REQUIRE_RCD_INTEGRATION", "1")
    else:
        monkeypatch.delenv("RIMSORT_REQUIRE_RCD_INTEGRATION", raising=False)
    outcome = pytest.fail.Exception if required else pytest.skip.Exception
    with pytest.raises(outcome, match="RIMSORT_RCD_LIBRARY"):
        enforce_integration_prerequisite()


def write_child_guard(path: Path) -> None:
    (path / "sitecustomize.py").write_text(
        "import socket\n"
        "from PySide6.QtWidgets import QApplication, QDialog\n"
        "def forbidden(*args, **kwargs):\n"
        "    raise RuntimeError('worker attempted network or GUI initialization')\n"
        "socket.socket.connect = forbidden\n"
        "socket.socket.connect_ex = forbidden\n"
        "QApplication.__init__ = forbidden\n"
        "QDialog.exec = forbidden\n"
        "QDialog.exec_ = forbidden\n",
        encoding="utf-8",
    )


def configure_child_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_child_guard(tmp_path)
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(tmp_path), str(root))))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def guarded_mods(
    qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, Path, Path]:
    widget, first, second = make_two_mod_list(qtbot, tmp_path)
    configure_child_guard(tmp_path, monkeypatch)
    return widget, first, second


def write_mod_files(first: Path, second: Path, defs_dir: str | None = None) -> None:
    for path, package in ((first, "example.first"), (second, "example.second")):
        (path / "About").mkdir()
        (path / "About" / "About.xml").write_text(
            f"<ModMetaData><name>{package}</name><packageId>{package}</packageId></ModMetaData>",
            encoding="utf-8",
        )
        if defs_dir is not None:
            defs = path / defs_dir
            defs.mkdir(parents=True)
            (defs / "Things.xml").write_text(
                f"<Defs><ThingDef><defName>Same</defName><label>{package}</label></ThingDef></Defs>",
                encoding="utf-8",
            )


def conflict_menu(
    mc: MainContent, widget: Any, settings: Any
) -> tuple[MenuBar, MenuBarController]:
    mc.mods_panel.active_mods_list = widget
    mc.metadata_controller = widget.metadata_controller
    menu = MenuBar(QMenuBar(), settings)
    controller = MenuBarController(menu, settings, lambda: None)
    return menu, controller


type IntegrationMenu = tuple[
    MainContent, MenuBar, MenuBarController, tuple[Any, Path, Path]
]


@pytest.fixture
def integration_menu(
    guarded_mods: tuple[Any, Path, Path],
    main_content: tuple[MainContent, list[bool]],
    mock_settings_controller: MagicMock,
) -> IntegrationMenu:
    mc = main_content[0]
    menu, controller = conflict_menu(
        mc, guarded_mods[0], mock_settings_controller.settings
    )
    return mc, menu, controller, guarded_mods


def wait_for_scan(qtbot: Any, dialog: Any) -> None:
    timer = QTimer(dialog)
    timer.setSingleShot(True)
    timer.timeout.connect(dialog.cancel_scan)
    timer.start(10000)
    try:
        qtbot.waitUntil(lambda: dialog.state != "running", timeout=11000)
    finally:
        timer.stop()
    assert dialog.state == "finished", dialog.state
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)


def select_note(qtbot: Any, dialog: Any, kind: str) -> None:
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    for row in range(dialog.notes.model.rowCount()):
        ref = dialog.notes.model.note(dialog.notes.model.index(row, 0))
        if ref is not None and ref.kind == kind:
            dialog.notes.table.selectRow(row)
            return
    raise AssertionError(f"note not found: {kind}")


def select_native_record(qtbot: Any, dialog: Any, index: int) -> None:
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    for row in range(dialog.notes.model.rowCount()):
        ref = dialog.notes.model.note(dialog.notes.model.index(row, 0))
        if ref is not None and ref.kind == "native" and ref.index == index:
            dialog.notes.table.selectRow(row)
            return
    raise AssertionError(f"native note not found: {index}")


@pytest.mark.parametrize(
    "selector",
    ["regular", "link", "dangling", "loop", "directory", "ambiguous", "malformed"],
)
def test_loadfolders_selector_policy_from_real_worker(
    qtbot: Any,
    require_integration: None,
    integration_menu: IntegrationMenu,
    selector: str,
) -> None:
    if (
        selector in {"link", "dangling", "loop", "ambiguous"}
        and sys.platform == "win32"
    ):
        pytest.skip("Unix symlink/case-sensitive fixture")
    mc, menu, controller, (widget, first, second) = integration_menu
    write_mod_files(first, second, "Custom/Defs")
    widget.metadata_controller.game_version = "1.7"
    xml = "<loadFolders><v1.7><li>Custom</li></v1.7></loadFolders>"
    for mod in (first, second):
        path = mod / "LoadFolders.xml"
        if selector == "regular":
            path.write_text(xml, encoding="utf-8")
        elif selector == "link":
            (mod / "folders.xml").write_text(xml, encoding="utf-8")
            path.symlink_to("folders.xml")
        elif selector == "dangling":
            path.symlink_to("missing.xml")
        elif selector == "loop":
            path.symlink_to("LoadFolders.xml")
        elif selector == "directory":
            path.mkdir()
        elif selector == "ambiguous":
            path.write_text(xml, encoding="utf-8")
            if (mod / "loadfolders.xml").exists():
                pytest.skip("case-sensitive filesystem required")
            (mod / "loadfolders.xml").write_text(xml, encoding="utf-8")
        else:
            path.write_text("<loadFolders><v1.7>", encoding="utf-8")
    menu.analyze_conflicts_action.trigger()
    dialog = mc.conflict_report_dialog
    assert dialog is not None
    wait_for_scan(qtbot, dialog)
    diagnostics = dialog.report["diagnostics"]
    if selector in {"regular", "link"}:
        assert len(dialog.report["conflicts"]) == 1
        assert not any(
            d.get("code", "").startswith("load_folders_") for d in diagnostics
        )
        assert not dialog.is_incomplete
    else:
        assert dialog.report["conflicts"] == []
        code = (
            "load_folders_parse_failure"
            if selector == "malformed"
            else "load_folders_inspection_failure"
        )
        index = next(i for i, d in enumerate(diagnostics) if d.get("code") == code)
        record = diagnostics[index]
        assert record["analysis_incomplete"]
        assert dialog.is_incomplete
        select_native_record(qtbot, dialog, index)
        assert str(first) in dialog.notes.details_view.toPlainText()
        if selector == "malformed":
            assert (
                str(first / "LoadFolders.xml")
                in dialog.notes.details_view.toPlainText()
            )
        assert dialog.notes.raw_view.toPlainText() == ""
        dialog.notes.raw_button.click()
        assert json.loads(dialog.notes.raw_view.toPlainText()) == record
    assert controller is not None


@pytest.mark.parametrize("shape", ["root", "nested", "valid", "mismatch", "missing_id"])
def test_unclosed_about_metadata_is_incomplete_from_real_worker(
    qtbot: Any, require_integration: None, integration_menu: IntegrationMenu, shape: str
) -> None:
    mc, menu, controller, (widget, first, second) = integration_menu
    write_mod_files(first, second)
    widget.metadata_controller.game_version = "1.7"
    prefix = "<ModMetaData><packageId>example.first</packageId>"
    xml = {
        "root": prefix,
        "nested": prefix + "<loadAfter><li>other</li>",
        "valid": prefix + "<optional/><unknown>ok</unknown></ModMetaData>",
        "mismatch": prefix + "<loadAfter></wrong></ModMetaData>",
        "missing_id": "<ModMetaData><name>First</name></ModMetaData>",
    }[shape]
    (first / "About/About.xml").write_text(xml, encoding="utf-8")
    menu.analyze_conflicts_action.trigger()
    dialog = mc.conflict_report_dialog
    assert dialog is not None
    wait_for_scan(qtbot, dialog)
    ids = [m["package_id"] for m in dialog.report["metadata"]["mods_scanned"]]
    assert "example.second" in ids
    if shape == "valid":
        assert "example.first" in ids
        assert not any(
            d.get("code") == "about_parse_failure" for d in dialog.report["diagnostics"]
        )
    else:
        assert "example.first" not in ids
        diagnostics = dialog.report["diagnostics"]
        index = next(
            i
            for i, d in enumerate(diagnostics)
            if d.get("code") == "about_parse_failure"
        )
        assert diagnostics[index]["severity"] == "error"
        assert diagnostics[index]["analysis_incomplete"]
        assert dialog.is_incomplete
        select_native_record(qtbot, dialog, index)
        assert str(first) in dialog.notes.details_view.toPlainText()
    assert controller is not None


@pytest.mark.parametrize("attributes", [("attr0", "attr1"), ("attr0", "attr0")])
def test_reconstruction_diagnostic_identity_from_real_worker(
    qtbot: Any,
    require_integration: None,
    integration_menu: IntegrationMenu,
    attributes: tuple[str, str],
) -> None:
    mc, menu, controller, (widget, first, second) = integration_menu
    write_mod_files(first, second, "Defs")
    widget.metadata_controller.game_version = "1.7"
    for mod, attribute in zip((first, second), attributes, strict=True):
        (mod / "Defs/Things.xml").write_text(
            f'<Defs><ThingDef {attribute}="&bogus;"><defName>Steel</defName></ThingDef></Defs>',
            encoding="utf-8",
        )
    menu.analyze_conflicts_action.trigger()
    dialog = mc.conflict_report_dialog
    assert dialog is not None
    wait_for_scan(qtbot, dialog)
    diagnostics = dialog.report["diagnostics"]
    matches = [
        (i, d)
        for i, d in enumerate(diagnostics)
        if d.get("code") == "xml_reconstruction_attribute_failure"
    ]
    assert [d["params"]["attribute"] for _, d in matches] == sorted(set(attributes))
    for index, record in matches:
        select_native_record(qtbot, dialog, index)
        assert dialog.notes.raw_view.toPlainText() == ""
        dialog.notes.raw_button.click()
        assert json.loads(dialog.notes.raw_view.toPlainText()) == record
    assert controller is not None


def test_child_guard_installed(tmp_path: Path) -> None:
    write_child_guard(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import socket,sitecustomize; from PySide6.QtWidgets import QApplication,QDialog; assert socket.socket.connect is sitecustomize.forbidden; assert socket.socket.connect_ex is sitecustomize.forbidden; assert QApplication.__init__ is sitecustomize.forbidden; assert QDialog.exec is sitecustomize.forbidden; assert QDialog.exec_ is sitecustomize.forbidden",
        ],
        env=os.environ | {"PYTHONPATH": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.parametrize("version, expected_conflicts", [("Unknown", 0), ("1.7", 1)])
def test_versioned_only_defs_are_qualified_when_version_unknown(
    qtbot: Any,
    require_integration: None,
    integration_menu: IntegrationMenu,
    version: str,
    expected_conflicts: int,
) -> None:
    mc, menu, controller, (widget, first, second) = integration_menu
    write_mod_files(first, second, "1.7/Defs")
    cast(MagicMock, widget.metadata_controller).game_version = version
    menu.analyze_conflicts_action.trigger()
    dialog = mc.conflict_report_dialog
    assert dialog is not None
    wait_for_scan(qtbot, dialog)
    assert len(dialog.report["conflicts"]) == expected_conflicts
    assert not any(d["analysis_incomplete"] for d in dialog.report["diagnostics"])
    assert dialog.is_incomplete is (version == "Unknown")
    if version == "Unknown":
        select_note(qtbot, dialog, "version")
        assert (
            dialog.tr(
                "Unknown game version: version-specific content may have been skipped."
            )
            in dialog.notes.details_view.toPlainText()
        )
    assert controller is not None


def test_real_ffi_scan_uses_unsaved_order(
    qtbot: Any,
    tmp_path: Path,
    require_integration: None,
    integration_menu: IntegrationMenu,
) -> None:
    mc, menu, controller, (widget, first, second) = integration_menu
    write_mod_files(first, second, "Defs")
    (tmp_path / "ModsConfig.xml").write_text(
        "<ModsConfigData><activeMods><li>example.first</li>"
        "<li>example.second</li></activeMods></ModsConfigData>",
        encoding="utf-8",
    )
    widget.insertItem(0, widget.takeItem(1))
    menu.analyze_conflicts_action.trigger()
    dialog = mc.conflict_report_dialog
    assert dialog is not None
    wait_for_scan(qtbot, dialog)
    qtbot.waitUntil(lambda: not dialog.browser.busy)
    report = dialog.report
    assert report["schema_version"] == 3
    assert report["metadata"]["order_aware"] is True
    assert report["conflicts"][0]["severity"] == "error"
    assert report["conflicts"][0]["winner"] == "example.first"
    dialog.table.selectRow(0)
    assert "example.first" in dialog.inspector.outcome_label.text()
    assert dialog.inspector._details_layout.count() == 0
    assert dialog.inspector.raw_view.toPlainText() == ""
    dialog.inspector.technical_button.click()
    labels = [
        label.text() for label in dialog.inspector._details_widget.findChildren(QLabel)
    ]
    assert any("Def type:" in text for text in labels)
    assert any("Package ID: example.first" in text for text in labels)
    assert dialog.inspector.raw_view.toPlainText() == ""
    dialog.inspector.raw_button.click()
    assert '"winner": "example.first"' in dialog.inspector.raw_view.toPlainText()
    assert controller is not None


def test_disappearing_mod_reports_incomplete_from_real_worker(
    qtbot: Any,
    monkeypatch: pytest.MonkeyPatch,
    require_integration: None,
    integration_menu: IntegrationMenu,
) -> None:
    mc, menu, controller, (_, first, second) = integration_menu
    write_mod_files(first, second)
    start = ConflictDetectorRunner.start

    def disappear(runner: ConflictDetectorRunner, request: dict[str, object]) -> None:
        (first / "About" / "About.xml").unlink()
        (first / "About").rmdir()
        first.rmdir()
        start(runner, request)

    monkeypatch.setattr(ConflictDetectorRunner, "start", disappear)
    menu.analyze_conflicts_action.trigger()
    dialog = mc.conflict_report_dialog
    assert dialog is not None
    qtbot.waitUntil(lambda: dialog.state != "running", timeout=10000)
    assert dialog.state == "finished", dialog.state
    qtbot.waitUntil(lambda: not dialog.notes.model.busy)
    assert dialog.is_incomplete
    assert dialog.report["conflicts"] == []
    assert any(
        d["analysis_incomplete"] and str(first) in d["message"]
        for d in dialog.report["diagnostics"]
    )
    assert "Incomplete" in dialog.status_label.text()
    select_note(qtbot, dialog, "native")
    assert str(first) in dialog.notes.details_view.toPlainText()
    assert controller is not None


def test_menu_cancel_stops_worker(
    qtbot: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    main_content: tuple[MainContent, list[bool]],
    mock_settings_controller: MagicMock,
    require_integration: None,
) -> None:
    widget, _, _ = make_two_mod_list(qtbot, tmp_path)
    configure_child_guard(tmp_path, monkeypatch)
    ready = tmp_path / "worker-ready"
    guard = tmp_path / "sitecustomize.py"
    guard.write_text(
        guard.read_text(encoding="utf-8")
        + "import os, threading\n"
        + "from pathlib import Path\n"
        + f"ready = Path({str(ready)!r})\n"
        + "pending = ready.with_suffix('.tmp')\n"
        + "pending.write_text(str(os.getpid()), encoding='utf-8')\n"
        + "pending.replace(ready)\n"
        + "threading.Event().wait()\n",
        encoding="utf-8",
    )
    mc = main_content[0]
    menu, controller = conflict_menu(mc, widget, mock_settings_controller.settings)
    owned_processes: list[QProcess] = []
    start = ConflictDetectorRunner.start

    def capture_process(
        runner: ConflictDetectorRunner, request: dict[str, object]
    ) -> None:
        try:
            start(runner, request)
        finally:
            if runner._process is not None:
                owned_processes.append(runner._process)

    monkeypatch.setattr(ConflictDetectorRunner, "start", capture_process)
    try:
        menu.analyze_conflicts_action.trigger()
        dialog = mc.conflict_report_dialog
        assert dialog is not None
        assert len(owned_processes) == 1
        started_process = owned_processes[0]
        assert isValid(started_process)
        assert started_process.waitForStarted(10000), started_process.errorString()
        qtbot.waitUntil(
            lambda: (
                ready.exists()
                or started_process.state() == QProcess.ProcessState.NotRunning
            ),
            timeout=10000,
        )
        assert ready.exists(), bytes(
            started_process.readAllStandardError().data()
        ).decode()
        assert started_process.state() == QProcess.ProcessState.Running
        assert started_process.processId() > 0
        assert int(ready.read_text(encoding="utf-8")) == started_process.processId()
        assert dialog.state == "running"
        finished_states: list[QProcess.ProcessState] = []
        started_process.finished.connect(
            lambda _code, _status: finished_states.append(started_process.state())
        )
        dialog.cancel_button.click()
        qtbot.waitUntil(lambda: bool(finished_states), timeout=10000)
        assert finished_states == [QProcess.ProcessState.NotRunning]
        qtbot.waitUntil(lambda: dialog.runner._process is None, timeout=10000)
        assert dialog.state == "cancelled"
        assert not dialog.report
        assert controller is not None
    finally:
        all_reaped = True
        for process in owned_processes:
            if isValid(process) and process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                if not (
                    process.waitForFinished(5000)
                    or not isValid(process)
                    or process.state() == QProcess.ProcessState.NotRunning
                ):
                    all_reaped = False
        assert all_reaped, "Failed to reap a cancellation test worker"


def test_menu_empty_active_list_is_not_clean_result(
    qtbot: Any,
    tmp_path: Path,
    main_content: tuple[MainContent, list[bool]],
    mock_settings_controller: MagicMock,
) -> None:
    widget, _, _ = make_two_mod_list(qtbot, tmp_path)
    widget.clear()
    mc = main_content[0]
    menu, controller = conflict_menu(mc, widget, mock_settings_controller.settings)
    menu.analyze_conflicts_action.trigger()
    dialog = mc.conflict_report_dialog
    assert dialog is not None
    assert dialog.state == "no_input"
    assert not dialog.report
    assert dialog.runner._process is None
    assert "No usable mod inputs" in dialog.status_label.text()
    assert controller is not None
