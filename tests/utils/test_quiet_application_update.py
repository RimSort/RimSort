"""Quiet application checks use the existing release lookup without dialogs."""

import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from textwrap import dedent
from threading import Event, get_ident
from unittest.mock import MagicMock

import pytest
import requests
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from app.models.settings import Settings
from app.utils import update_utils
from app.utils.app_info import AppInfo
from app.utils.update_utils import UpdateManager


@pytest.fixture
def updater(monkeypatch: pytest.MonkeyPatch) -> Generator[UpdateManager]:
    monkeypatch.delenv("RIMSORT_DISABLE_UPDATER", raising=False)
    monkeypatch.setattr(update_utils, "__compiled__", object(), raising=False)
    AppInfo()._app_version = "1.0.0"
    content = MagicMock()
    content.do_threaded_loading_animation.side_effect = lambda **kwargs: kwargs[
        "target"
    ]()
    manager = UpdateManager(Settings(), content)
    yield manager
    thread = getattr(manager, "_quiet_check_thread", None)
    if thread is not None:
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.fixture
def release_response(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {
        "tag_name": "v1.1.0",
        "assets": [
            {"name": name, "browser_download_url": "https://example.com/RimSort"}
            for name in (
                "RimSort-v1.1.0-Darwin_arm64.tar.gz",
                "RimSort-v1.1.0-Darwin_x86_64.tar.gz",
                "RimSort-v1.1.0-Windows_x86_64.zip",
                "RimSort-v1.1.0-Ubuntu-24.04_x86_64.tar.gz",
            )
        ],
    }
    monkeypatch.setattr(update_utils.http, "get", MagicMock(return_value=response))
    return response


def test_quiet_check_keeps_event_loop_responsive_and_coalesces_requests(
    updater: UpdateManager,
    release_response: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
) -> None:
    started = Event()
    release = Event()
    heartbeat = Event()
    request_threads: list[int] = []

    def fetch(*_args: object, **_kwargs: object) -> MagicMock:
        request_threads.append(get_ident())
        started.set()
        assert release.wait(5)
        return release_response

    get = MagicMock(side_effect=fetch)
    monkeypatch.setattr(update_utils.http, "get", get)
    try:
        with qtbot.waitSignal(updater.update_available, timeout=3000) as signal:
            updater._check_for_update_silently()
            assert started.wait(1)
            updater._check_for_update_silently()
            QTimer.singleShot(0, heartbeat.set)
            qtbot.waitUntil(heartbeat.is_set)
            assert len(request_threads) == 1
            assert request_threads[0] != get_ident()
            assert updater._quiet_check_thread is not None
            assert updater._quiet_check_thread.daemon
            release.set()
        assert signal.args == ["v1.1.0"]
        get.assert_called_once()
    finally:
        release.set()


@pytest.mark.parametrize(
    "case",
    [
        "new",
        "equal",
        "older",
        "unknown",
        "invalid-current",
        "offline",
        "rate-limit",
        "invalid-tag",
        "no-asset",
        "invalid-json",
    ],
)
def test_background_results_never_open_dialogs(
    updater: UpdateManager,
    release_response: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    if case == "equal":
        AppInfo()._app_version = "1.1.0"
    elif case == "older":
        AppInfo()._app_version = "1.2.0"
    elif case in {"unknown", "invalid-current"}:
        AppInfo()._app_version = "Unknown version" if case == "unknown" else "invalid"
    elif case == "offline":
        release_response.raise_for_status.side_effect = requests.ConnectionError(
            "offline"
        )
    elif case == "rate-limit":
        response = requests.Response()
        response.status_code = 429
        release_response.raise_for_status.side_effect = requests.HTTPError(
            response=response
        )
    elif case == "invalid-tag":
        release_response.json.return_value["tag_name"] = "invalid"
    elif case == "no-asset":
        release_response.json.return_value["assets"] = []
    elif case == "invalid-json":
        release_response.json.side_effect = ValueError("invalid JSON")

    dialogs = MagicMock()
    monkeypatch.setattr(update_utils.dialogue, "show_warning", dialogs)
    monkeypatch.setattr(update_utils.dialogue, "show_dialogue_conditional", dialogs)
    internet = MagicMock()
    monkeypatch.setattr(update_utils.http, "head", internet)
    loading = MagicMock()
    monkeypatch.setattr(
        updater, "main_content", MagicMock(do_threaded_loading_animation=loading)
    )
    install = MagicMock()
    monkeypatch.setattr(updater, "_handle_update_process", install)
    tags: list[str] = []
    updater.update_available.connect(tags.append)

    updater._quiet_check_worker()

    assert tags == (
        ["v1.1.0"] if case == "new" else [""] if case in {"equal", "older"} else []
    )
    dialogs.assert_not_called()
    internet.assert_not_called()
    loading.assert_not_called()
    install.assert_not_called()


@pytest.mark.parametrize("disabled", ["environment", "source"])
def test_quiet_check_respects_updater_disable_conditions(
    updater: UpdateManager,
    release_response: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    disabled: str,
) -> None:
    if disabled == "environment":
        monkeypatch.setenv("RIMSORT_DISABLE_UPDATER", "1")
    else:
        monkeypatch.delattr(update_utils, "__compiled__")

    updater._check_for_update_silently()

    assert updater._quiet_check_thread is None
    release_response.raise_for_status.assert_not_called()


@pytest.mark.parametrize("accept", [False, True])
def test_explicit_checks_still_prompt_and_only_install_after_accepting(
    updater: UpdateManager,
    release_response: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    accept: bool,
) -> None:
    monkeypatch.setattr(updater, "_validate_prerequisites", lambda: True)
    monkeypatch.setattr(updater, "_check_needs_elevation", lambda: False)
    prompt = MagicMock(
        return_value=QMessageBox.StandardButton.Yes
        if accept
        else QMessageBox.StandardButton.No
    )
    monkeypatch.setattr(update_utils.dialogue, "show_dialogue_conditional", prompt)
    install = MagicMock()
    monkeypatch.setattr(updater, "_handle_update_process", install)

    updater.do_check_for_update()

    prompt.assert_called_once()
    assert install.call_count == int(accept)


def test_destroyed_sender_during_check_does_not_crash(
    updater: UpdateManager,
    release_response: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
) -> None:
    started = Event()
    release = Event()

    def fetch(*_args: object, **_kwargs: object) -> MagicMock:
        started.set()
        assert release.wait(5)
        return release_response

    monkeypatch.setattr(update_utils.http, "get", fetch)
    try:
        updater._check_for_update_silently()
        assert started.wait(1)
        with qtbot.waitSignal(updater.destroyed):
            updater.deleteLater()
    finally:
        release.set()


def test_worker_start_failure_is_quiet(
    updater: UpdateManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    thread = MagicMock()
    thread.start.side_effect = RuntimeError("Cannot start thread")
    monkeypatch.setattr(
        update_utils.threading, "Thread", MagicMock(return_value=thread)
    )

    updater._check_for_update_silently()

    assert updater._quiet_check_thread is None
    thread.start.assert_called_once()


def test_process_can_exit_with_a_check_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RIMSORT_DEV", "1")
    monkeypatch.setenv("RIMSORT_DEV_DIR", str(tmp_path))
    monkeypatch.delenv("RIMSORT_DISABLE_UPDATER", raising=False)
    monkeypatch.delenv("APPIMAGE", raising=False)
    script = dedent(
        """
        from threading import Event
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from app.models.settings import Settings
        from app.utils import update_utils
        from app.utils.app_info import AppInfo

        app = QApplication([])
        update_utils.__compiled__ = True
        AppInfo()._app_version = "1.0.0"
        started = Event()
        blocked = Event()
        def fetch(*args, **kwargs):
            started.set()
            blocked.wait()
        update_utils.http.get = fetch
        updater = update_utils.UpdateManager(Settings(), None)
        updater._check_for_update_silently()
        assert started.wait(2)
        QTimer.singleShot(0, app.quit)
        app.exec()
        print("closed-with-check-in-flight")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "closed-with-check-in-flight" in result.stdout
