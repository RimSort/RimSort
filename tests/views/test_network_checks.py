"""Network checks must keep processing UI events before results are available."""

import json
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock

import pytest
import requests
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
from pytestqt.qtbot import QtBot

from app.controllers.main_content_controller import MainContentController
from app.models.animations import LoadingAnimation
from app.models.metadata.metadata_structure import AboutXmlMod, ModType
from app.utils import http, update_utils
from app.utils.app_info import AppInfo
from app.utils.http_downloader import DownloadResult, HttpDatabaseDownloader
from app.utils.steam import workshop_utils
from app.views.main_content_panel import MainContent


@pytest.fixture
def network_window(
    main_content: tuple[MainContent, list[bool]], qtbot: QtBot
) -> Generator[tuple[QMainWindow, MainContent, list[bool]]]:
    content, _ = main_content
    AppInfo()._theme_data_folder = Path(__file__).resolve().parents[2] / "themes"
    window = QMainWindow()
    window.setCentralWidget(content.main_layout_frame)
    qtbot.addWidget(window)
    window.show()
    enabled: list[bool] = []
    content.disable_enable_widgets_signal.connect(enabled.append)
    yield window, content, enabled
    window.close()


def _inspect_loading(
    qtbot: QtBot,
    window: QMainWindow,
    started: Event,
    release: Event,
    inspected: list[str],
) -> None:
    def inspect() -> None:
        try:
            qtbot.waitUntil(started.is_set)
            qtbot.waitUntil(
                lambda: any(
                    label.isVisible()
                    for label in window.findChildren(QLabel, "loadingAnimationString")
                )
            )
            inspected.extend(
                label.text()
                for label in window.findChildren(QLabel, "loadingAnimationString")
                if label.isVisible()
            )
        finally:
            release.set()

    QTimer.singleShot(0, inspect)


@pytest.mark.parametrize("failure", [False, True])
def test_workshop_check_uses_worker_without_preflight(
    network_window: tuple[QMainWindow, MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    failure: bool,
) -> None:
    window, content, enabled = network_window
    mod = AboutXmlMod()
    mod.mod_path = Path("/fake/workshop/123")
    mod._mod_type = ModType.STEAM_WORKSHOP
    mod.__dict__["published_file_id"] = "123"
    content.metadata_controller.mods_metadata.update({str(mod.mod_path): mod})
    head = MagicMock(return_value=requests.Response())
    monkeypatch.setattr(http, "head", head)
    started, release = Event(), Event()
    threads: list[bool] = []
    inspected: list[str] = []

    def query(pfids: list[str]) -> tuple[list[dict[str, str]], list[str], list[str]]:
        threads.append(QThread.currentThread() == content.thread())
        started.set()
        assert release.wait(5)
        assert pfids == ["123"]
        if failure:
            return [], pfids, ["Timed out"]
        return [], [], []

    monkeypatch.setattr(
        workshop_utils, "ISteamRemoteStorage_GetPublishedFileDetails", query
    )
    warning = MagicMock()
    monkeypatch.setattr(workshop_utils, "show_warning", warning)
    monkeypatch.setattr("app.views.main_content_panel.dialogue.show_warning", warning)
    # No available updates: preserve the normal result path without opening a panel.
    panel = MagicMock()
    panel.return_value._row_count.return_value = 0
    monkeypatch.setattr("app.views.main_content_panel.WorkshopModUpdaterPanel", panel)

    _inspect_loading(qtbot, window, started, release, inspected)
    content._do_check_for_workshop_updates()
    assert threads == [False]
    assert inspected == ["Checking Steam Workshop mods for updates..."]
    head.assert_not_called()
    assert enabled == [False, True]
    assert warning.call_count == int(failure)


@pytest.mark.parametrize("failure", [False, True])
def test_release_check_keeps_events_and_restores_controls(
    network_window: tuple[QMainWindow, MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    failure: bool,
) -> None:
    window, content, enabled = network_window
    manager = update_utils.UpdateManager(content.settings, content)
    started, release = Event(), Event()
    threads: list[bool] = []
    inspected: list[str] = []
    warning_threads: list[bool] = []
    monkeypatch.setattr(manager, "_validate_prerequisites", lambda: True)
    monkeypatch.setattr(manager, "_check_needs_elevation", lambda: False)
    monkeypatch.setattr(manager, "_prompt_user_for_update", lambda *args: True)
    install = MagicMock()
    monkeypatch.setattr(manager, "_handle_update_process", install)
    monkeypatch.setattr(
        manager,
        "_get_platform_download_url",
        lambda *args: {"url": "https://example.invalid/update.zip"},
    )

    def get(url: str, **kwargs: object) -> requests.Response:
        threads.append(QThread.currentThread() == content.thread())
        started.set()
        if not threads[-1]:
            assert release.wait(5)
        if failure:
            raise requests.ConnectTimeout("Timed out")
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"tag_name": "v999.0.0", "assets": []}).encode()
        return response

    def warn(**kwargs: object) -> None:
        warning_threads.append(QThread.currentThread() == content.thread())

    monkeypatch.setattr(http, "get", get)
    monkeypatch.setattr(update_utils.dialogue, "show_warning", warn)

    _inspect_loading(qtbot, window, started, release, inspected)
    manager.do_check_for_update()
    QApplication.processEvents()
    assert threads == [False]
    assert inspected == ["Checking for RimSort updates..."]
    assert enabled == [False, True]
    assert content.mod_info_panel.info_panel_frame.isVisible()
    assert warning_threads == ([True] if failure else [])
    assert install.call_count == int(not failure)


def test_updater_prerequisites_do_not_probe_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = update_utils.UpdateManager(MagicMock(), None)
    monkeypatch.setattr(update_utils, "__compiled__", object(), raising=False)
    monkeypatch.delenv("RIMSORT_DISABLE_UPDATER", raising=False)
    head = MagicMock(return_value=requests.Response())
    monkeypatch.setattr(http, "head", head)
    assert manager._validate_prerequisites()
    head.assert_not_called()


@pytest.mark.parametrize("result", [DownloadResult.UP_TO_DATE, DownloadResult.FAILED])
def test_startup_database_download_dispatches_without_preflight(
    result: DownloadResult,
    network_window: tuple[QMainWindow, MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
) -> None:
    _, content, _ = network_window
    monkeypatch.setattr(
        MainContentController, "_start_github_update_check", lambda self: None
    )
    controller = MainContentController(
        content, content.settings, content.metadata_controller
    )
    controller.settings.update_databases_on_startup = True
    head = MagicMock(return_value=requests.Response())
    monkeypatch.setattr(http, "head", head)
    started, release = Event(), Event()
    threads: list[bool] = []
    statuses: list[str] = []
    content.status_signal.connect(statuses.append)

    def download(
        self: HttpDatabaseDownloader, **kwargs: object
    ) -> tuple[DownloadResult, str | None]:
        threads.append(QThread.currentThread() == content.thread())
        started.set()
        assert release.wait(5)
        return result, "Timed out" if result == DownloadResult.FAILED else None

    monkeypatch.setattr(HttpDatabaseDownloader, "download", download)
    try:
        controller._update_databases_on_startup_if_enabled_silent()
        qtbot.waitUntil(started.is_set)
        assert threads == [False]
        assert statuses
        head.assert_not_called()
    finally:
        release.set()
        worker = controller._http_download_worker
        if worker is not None:
            qtbot.waitUntil(lambda: not worker.isRunning())
            QApplication.processEvents()
    assert statuses[-1] == (
        "Failed to update databases"
        if result == DownloadResult.FAILED
        else "Database updates finished"
    )


@pytest.mark.parametrize("worker_finished", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_closing_during_release_check_does_not_show_result(
    network_window: tuple[QMainWindow, MainContent, list[bool]],
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    worker_finished: bool,
    failure: bool,
) -> None:
    window, content, _ = network_window
    manager = update_utils.UpdateManager(content.settings, content)
    monkeypatch.setattr(manager, "_validate_prerequisites", lambda: True)
    monkeypatch.setattr(manager, "_check_needs_elevation", lambda: False)
    started, release = Event(), Event()
    warning = MagicMock()
    monkeypatch.setattr(update_utils.dialogue, "show_warning", warning)
    install = MagicMock()
    monkeypatch.setattr(manager, "_handle_update_process", install)
    prompt = MagicMock(return_value=True)
    monkeypatch.setattr(manager, "_prompt_user_for_update", prompt)
    monkeypatch.setattr(
        manager,
        "_get_platform_download_url",
        lambda *args: {"url": "https://example.invalid/update.zip"},
    )

    def get(url: str, **kwargs: object) -> requests.Response:
        started.set()
        assert release.wait(5)
        if failure:
            raise requests.ConnectTimeout("Timed out after window closed")
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"tag_name": "v999.0.0", "assets": []}).encode()
        return response

    monkeypatch.setattr(http, "get", get)
    workers: list[QThread] = []

    def close() -> None:
        qtbot.waitUntil(started.is_set)
        animation = window.findChild(LoadingAnimation)
        assert animation is not None
        workers.append(animation._thread)
        if worker_finished:
            release.set()
            qtbot.waitUntil(lambda: animation.animation_finished)
        content.abort_loading()
        window.close()
        release.set()

    QTimer.singleShot(0, close)
    try:
        manager.do_check_for_update()
        assert not window.isVisible()
        warning.assert_not_called()
        install.assert_not_called()
        prompt.assert_not_called()
    finally:
        release.set()
        for worker in workers:
            qtbot.waitUntil(worker.isFinished)
        QApplication.processEvents()
    warning.assert_not_called()


@pytest.mark.parametrize("startup", [False, True])
def test_loading_shutdown_finishes_pending_worker(
    tmp_path: Path, startup: bool
) -> None:
    """Exercise Qt teardown, including initialization before QApplication.exec()."""
    code = """
import os
import sys
from pathlib import Path
from threading import Event, Timer
from types import SimpleNamespace

os.environ['RIMSORT_DEV'] = '1'
os.environ['RIMSORT_DEV_DIR'] = sys.argv[1]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from app.views.main_content_panel import MainContent

app = QApplication([])
started, release, completed = Event(), Event(), Event()
class Content(QObject):
    disable_enable_widgets_signal = Signal(bool)
    do_threaded_loading_animation = MainContent.do_threaded_loading_animation
    abort_loading = MainContent.abort_loading
    def __init__(self):
        super().__init__()
        self._active_loading_loop = None
        self.panel = QWidget()
        layout = QVBoxLayout(self.panel)
        frame = QWidget()
        layout.addWidget(frame)
        self.mod_info_panel = SimpleNamespace(info_panel_frame=frame, panel=layout)
content = Content()
class Window(QMainWindow):
    def closeEvent(self, event):
        content.abort_loading()
        event.accept()
window = Window()
window.setCentralWidget(content.panel)
window.show()
def target():
    started.set()
    assert release.wait(5)
    completed.set()
def close():
    if not started.is_set():
        QTimer.singleShot(1, close)
        return
    window.close()
    timer = Timer(0.2, release.set)
    timer.daemon = True
    timer.start()
def load():
    gif = str(Path.cwd() / 'themes/default-icons/rimsort.gif')
    assert content.do_threaded_loading_animation(gif, target, 'Checking...') is None
QTimer.singleShot(0, close)
if sys.argv[2] == 'True':
    load()
else:
    QTimer.singleShot(0, load)
    app.exec()
assert completed.is_set()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path), str(startup)],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
