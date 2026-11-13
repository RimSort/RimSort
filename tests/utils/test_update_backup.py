"""Application updates must preserve a usable backup and respect user decisions."""

import builtins
import os
import threading
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from app.models.settings import Settings
from app.utils import update_utils
from app.utils.app_info import AppInfo
from app.utils.update_utils import UpdateManager
from app.views.task_progress_window import TaskProgressWindow


@pytest.fixture
def update_manager(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[UpdateManager]:
    settings = Settings()
    settings.enable_backup_before_update = True
    settings.max_backups = 1
    manager = UpdateManager(settings, None)
    (AppInfo().application_folder / "RimSort").write_bytes(b"working application")
    AppInfo().application_backups_folder.mkdir(parents=True)
    stage = tmp_path / "stage"
    stage.mkdir()

    def download(_url: str) -> None:
        manager._update_content = b"x" * 2048

    def extract(*_args: object) -> None:
        manager._extracted_path = stage

    monkeypatch.setattr(manager, "_download_update", download)
    monkeypatch.setattr(manager, "_extract_update_with_progress", extract)
    monkeypatch.setattr(manager, "_check_needs_elevation", lambda: False)
    yield manager
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, TaskProgressWindow):
            qtbot.addWidget(widget)
            widget.close()


def _old_backup() -> Path:
    path = AppInfo().application_backups_folder / "RimSort_Backup_20000101.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("RimSort", b"old complete application")
    os.utime(path, (1, 1))
    return path


def _perform_update(manager: UpdateManager) -> None:
    manager._perform_update("https://example.invalid/update.zip", "v99.0.0", False)


@pytest.mark.parametrize("proceed", [False, True])
@pytest.mark.parametrize("failure", ["whole_backup", "individual_file"])
def test_backup_failure_respects_decision_and_preserves_old_backup(
    update_manager: UpdateManager,
    monkeypatch: pytest.MonkeyPatch,
    proceed: bool,
    failure: str,
) -> None:
    old_backup = _old_backup()
    launch = MagicMock()
    monkeypatch.setattr(update_manager, "_launch_update_script", launch)
    prompt_threads: list[int] = []

    def answer(*, title: str, **_kwargs: object) -> QMessageBox.StandardButton:
        if title == update_utils.ERR_BACKUP_FAILED_TITLE:
            prompt_threads.append(threading.get_ident())
            return (
                QMessageBox.StandardButton.Yes
                if proceed
                else QMessageBox.StandardButton.No
            )
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(update_utils.dialogue, "show_dialogue_conditional", answer)
    if failure == "whole_backup":
        monkeypatch.setattr(
            update_utils,
            "create_zip_backup",
            MagicMock(side_effect=OSError("Disk full")),
        )
    else:
        real_open = builtins.open
        executable = AppInfo().application_folder / "RimSort"

        def unreadable(file: object, *args: object, **kwargs: object) -> object:
            if file == executable:
                raise PermissionError("Unreadable application executable")
            return real_open(file, *args, **kwargs)  # type: ignore[call-overload]

        monkeypatch.setattr(builtins, "open", unreadable)

    _perform_update(update_manager)

    assert launch.call_count == int(proceed)
    assert prompt_threads == [threading.get_ident()]
    assert list(AppInfo().application_backups_folder.iterdir()) == [old_backup]
    with ZipFile(old_backup) as archive:
        assert archive.read("RimSort") == b"old complete application"


def test_successful_backup_is_complete_then_prunes_old_backup(
    update_manager: UpdateManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_backup = _old_backup()
    main_thread = threading.get_ident()
    progress_threads: list[int] = []
    real_update_progress = TaskProgressWindow.update_progress

    def record_progress(
        widget: TaskProgressWindow, percent: int, message: str = ""
    ) -> None:
        progress_threads.append(threading.get_ident())
        real_update_progress(widget, percent, message)

    def launch(*_args: object) -> None:
        assert not old_backup.exists()
        backups = list(AppInfo().application_backups_folder.glob("*.zip"))
        assert len(backups) == 1
        with ZipFile(backups[0]) as archive:
            assert archive.read("RimSort") == b"working application"

    installer = MagicMock(side_effect=launch)
    monkeypatch.setattr(TaskProgressWindow, "update_progress", record_progress)
    monkeypatch.setattr(update_manager, "_launch_update_script", installer)
    monkeypatch.setattr(
        update_utils.dialogue,
        "show_dialogue_conditional",
        lambda **_kwargs: QMessageBox.StandardButton.Yes,
    )
    _perform_update(update_manager)
    installer.assert_called_once()
    assert progress_threads and set(progress_threads) == {main_thread}


def test_update_skips_backup_when_disabled(
    update_manager: UpdateManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    update_manager.settings.enable_backup_before_update = False
    backup = MagicMock()
    installer = MagicMock()
    monkeypatch.setattr(update_manager, "_create_backup_with_progress", backup)
    monkeypatch.setattr(update_manager, "_launch_update_script", installer)
    monkeypatch.setattr(
        update_utils.dialogue,
        "show_dialogue_conditional",
        lambda **_kwargs: QMessageBox.StandardButton.Yes,
    )
    _perform_update(update_manager)
    backup.assert_not_called()
    installer.assert_called_once()


def test_backup_timeout_waits_for_worker_and_stops_update(
    update_manager: UpdateManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_backup = _old_backup()
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    installer = MagicMock()
    warning = MagicMock()
    original_backup = update_utils.create_zip_backup

    def slow_backup(*args: object, **kwargs: object) -> None:
        started.set()
        assert release.wait(3), "Test backup worker was not released"
        try:
            original_backup(*args, **kwargs)  # type: ignore[arg-type]
        finally:
            finished.set()

    observed_wait = []

    def release_after_timeout() -> None:
        widget = update_manager._progress_widget
        if (
            started.is_set()
            and not release.is_set()
            and widget is not None
            and widget.message_label is not None
            and "timed out" in widget.message_label.text()
        ):
            observed_wait.append(not finished.is_set())
            installer.assert_not_called()
            release.set()

    timer = QTimer()
    timer.timeout.connect(release_after_timeout)
    timer.start(1)
    monkeypatch.setattr(update_utils, "BACKUP_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(update_utils, "create_zip_backup", slow_backup)
    monkeypatch.setattr(update_utils.dialogue, "show_warning", warning)
    monkeypatch.setattr(update_manager, "_launch_update_script", installer)
    monkeypatch.setattr(
        update_utils.dialogue,
        "show_dialogue_conditional",
        lambda **_kwargs: QMessageBox.StandardButton.Yes,
    )
    try:
        _perform_update(update_manager)
    finally:
        release.set()
        timer.stop()

    assert observed_wait and all(observed_wait)
    assert finished.is_set()
    installer.assert_not_called()
    warning.assert_called_once()
    assert list(AppInfo().application_backups_folder.iterdir()) == [old_backup]


def test_backup_completes_before_event_loop_starts(
    update_manager: UpdateManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ImmediateWorker(update_utils._BackupWorker):
        def start(
            self, priority: QThread.Priority = QThread.Priority.InheritPriority
        ) -> None:
            super().start(priority)
            assert self.wait(3000)

    monkeypatch.setattr(update_utils, "_BackupWorker", ImmediateWorker)
    installer = MagicMock()
    monkeypatch.setattr(update_manager, "_launch_update_script", installer)
    monkeypatch.setattr(
        update_utils.dialogue,
        "show_dialogue_conditional",
        lambda **_kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(update_utils, "BACKUP_TIMEOUT_SECONDS", 0.2)
    warning = MagicMock()
    monkeypatch.setattr(update_utils.dialogue, "show_warning", warning)
    _perform_update(update_manager)
    installer.assert_called_once()
    warning.assert_not_called()


def test_shutdown_during_backup_stops_without_prompt(
    update_manager: UpdateManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_backup = _old_backup()
    original_backup = update_utils.create_zip_backup
    started = threading.Event()
    release = threading.Event()

    def backup(*args: object, **kwargs: object) -> None:
        started.set()
        assert release.wait(3)
        original_backup(*args, **kwargs)  # type: ignore[arg-type]

    def shutdown() -> None:
        if started.is_set() and not release.is_set():
            app = QApplication.instance()
            assert app is not None
            app.aboutToQuit.emit()
            release.set()

    timer = QTimer()
    timer.timeout.connect(shutdown)
    timer.start(1)
    installer = MagicMock()
    prompt = MagicMock(return_value=QMessageBox.StandardButton.Yes)
    warning = MagicMock()
    monkeypatch.setattr(update_utils, "create_zip_backup", backup)
    monkeypatch.setattr(update_manager, "_launch_update_script", installer)
    monkeypatch.setattr(update_utils.dialogue, "show_dialogue_conditional", prompt)
    monkeypatch.setattr(update_utils.dialogue, "show_warning", warning)
    try:
        _perform_update(update_manager)
    finally:
        release.set()
        timer.stop()
    installer.assert_not_called()
    assert prompt.call_count == 1  # Only the download confirmation precedes shutdown.
    warning.assert_not_called()
    assert list(AppInfo().application_backups_folder.iterdir()) == [old_backup]
