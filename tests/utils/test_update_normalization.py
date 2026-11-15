"""Normalization completion must survive both sides of event-loop entry."""

import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFrame, QVBoxLayout, QWidget
from pytestqt.qtbot import QtBot

from app.models.settings import Settings
from app.utils import update_utils
from app.utils.app_info import AppInfo
from app.utils.update_utils import UpdateExtractionError, UpdateManager
from app.views.task_progress_window import TaskProgressWindow


@pytest.fixture
def manager(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> UpdateManager:
    real_window = TaskProgressWindow

    def progress(
        title: str, show_message: bool, show_percent: bool
    ) -> TaskProgressWindow:
        widget = real_window(title, show_message, show_percent)
        qtbot.addWidget(widget)
        return widget

    monkeypatch.setattr(update_utils, "TaskProgressWindow", progress)
    return UpdateManager(Settings(), MagicMock())


@pytest.fixture
def guarded_loop(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    expired: list[bool] = []

    class GuardedLoop(QEventLoop):
        def exec(
            self,
            flags: QEventLoop.ProcessEventsFlag = QEventLoop.ProcessEventsFlag.AllEvents,
        ) -> int:
            timer = QTimer(self)
            timer.setSingleShot(True)

            def timeout() -> None:
                expired.append(True)
                self.quit()

            timer.timeout.connect(timeout)
            timer.start(1000)
            try:
                return super().exec(flags)
            finally:
                timer.stop()

    monkeypatch.setattr(update_utils, "QEventLoop", GuardedLoop)
    return expired


def prepare(
    manager: UpdateManager,
    qtbot: QtBot,
    tmp_path: Path,
    system: str,
    embedded: bool,
    failure: bool,
) -> tuple[Path, Path]:
    manager._system = system
    base = tmp_path / "extracted"
    wrapper = base / "release-wrapper"
    executable = wrapper / (
        "RimSort.app/Contents/MacOS/RimSort"
        if system == "Darwin"
        else "RimSort.exe"
        if system == "Windows"
        else "RimSort"
    )
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"application")
    (wrapper / "data.txt").write_text("preserve")
    if failure:
        executable.unlink()
    if embedded:
        parent = QWidget()
        qtbot.addWidget(parent)
        layout = QVBoxLayout(parent)
        frame = QFrame()
        layout.addWidget(frame)
        parent.show()
        manager.mod_info_panel = SimpleNamespace(
            info_panel_frame=frame, panel=layout, window=parent
        )
    return base, base / executable.relative_to(wrapper)


def check_cleanup(manager: UpdateManager) -> None:
    assert manager._progress_widget is not None
    assert not manager._progress_widget.isVisible()
    if manager.mod_info_panel:
        assert manager.mod_info_panel.info_panel_frame.isVisible()
        assert manager.mod_info_panel.panel.indexOf(manager._progress_widget) == -1


@pytest.mark.parametrize("system", ["Darwin", "Windows", "Linux"])
@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_completion_before_loop_entry(
    manager: UpdateManager,
    guarded_loop: list[bool],
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    tmp_path: Path,
    system: str,
    embedded: bool,
    failure: bool,
) -> None:
    base, executable = prepare(manager, qtbot, tmp_path, system, embedded, failure)
    workers: list[Thread] = []

    class EarlyThread(Thread):
        def start(self) -> None:
            workers.append(self)
            super().start()
            self.join(timeout=5)
            assert not self.is_alive(), "Normalization worker did not finish"

    monkeypatch.setattr(update_utils.threading, "Thread", EarlyThread)
    if failure:
        with pytest.raises(UpdateExtractionError, match="executable"):
            manager._normalize_structure(base, 2)
    else:
        manager._normalize_structure(base, 2)
        assert executable.read_bytes() == b"application"
        assert (base / "data.txt").read_text() == "preserve"
        assert not (base / "release-wrapper").exists()

    assert len(workers) == 1
    assert not workers[0].is_alive()
    assert not guarded_loop, "Completion was lost; only the watchdog released the loop"
    check_cleanup(manager)


@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_completion_after_loop_entry_keeps_gui_responsive(
    manager: UpdateManager,
    guarded_loop: list[bool],
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    tmp_path: Path,
    embedded: bool,
    failure: bool,
) -> None:
    base, executable = prepare(manager, qtbot, tmp_path, "Linux", embedded, failure)
    released = Event()
    heartbeat: list[bool] = []
    normalize = manager._normalize_extracted_structure

    def controlled(path: Path, count: int) -> None:
        assert released.wait(5), "GUI did not process the release event"
        normalize(path, count)

    def release() -> None:
        heartbeat.append(True)
        released.set()

    monkeypatch.setattr(manager, "_normalize_extracted_structure", controlled)
    QTimer.singleShot(0, release)
    try:
        if failure:
            with pytest.raises(UpdateExtractionError, match="executable"):
                manager._normalize_structure(base, 2)
        else:
            manager._normalize_structure(base, 2)
            assert executable.read_bytes() == b"application"
    finally:
        released.set()
    assert heartbeat == [True]
    assert not guarded_loop
    check_cleanup(manager)


@pytest.mark.parametrize("embedded", [False, True])
def test_thread_start_failure_cleans_progress(
    manager: UpdateManager,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    tmp_path: Path,
    embedded: bool,
) -> None:
    base, _ = prepare(manager, qtbot, tmp_path, "Linux", embedded, False)

    def fail_start(_thread: Thread) -> None:
        raise RuntimeError("Cannot start worker")

    monkeypatch.setattr(Thread, "start", fail_start)
    with pytest.raises(RuntimeError, match="Cannot start worker"):
        manager._normalize_structure(base, 2)
    check_cleanup(manager)


def _shutdown_probe(root: Path, failure: bool, before: bool) -> None:
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    manager = UpdateManager(Settings(), MagicMock())
    manager._system = "Linux"
    source = root / "extracted"
    archive = BytesIO()
    with ZipFile(archive, "w") as output:
        output.writestr("release-wrapper/data.txt", "preserve")
        if not failure:
            output.writestr("release-wrapper/RimSort", b"application")
    started, released, completed = Event(), Event(), Event()
    download_released, download_finished = Event(), Event()
    normalize = manager._normalize_extracted_structure
    normalizing = manager._normalize_structure
    original_join = Thread.join
    state: dict[str, object] = {}
    side_effects: list[str] = []

    def new_temp() -> Path:
        source.mkdir(parents=True)
        return source

    def download(_url: str) -> None:
        try:
            if not download_released.wait(5):
                raise RuntimeError("Download stage did not process GUI events")
            manager._update_content = archive.getvalue()
            manager.download_complete.emit(True, "")
        finally:
            download_finished.set()

    def controlled(path: Path, count: int) -> None:
        started.set()
        try:
            if not released.wait(5):
                raise RuntimeError("Shutdown did not release the worker")
            normalize(path, count)
        finally:
            completed.set()

    def join(thread: Thread, timeout: float | None = None) -> None:
        released.set()
        original_join(thread, timeout)

    def shutdown() -> None:
        if not started.wait(5):
            state["error"] = "Worker never started"
            released.set()
        app.quit()

    def start() -> None:
        try:
            manager._perform_update(
                "https://example.invalid/update.zip", "v1.0.0", False
            )
        except Exception as error:
            state["error"] = str(error)
        finally:
            state["completed_at_return"] = completed.is_set()
            released.set()
            app.quit()

    def normalize_stage(path: Path, count: int) -> None:
        if before:
            app.quit()
        else:
            QTimer.singleShot(0, shutdown)
        normalizing(path, count)

    QTimer.singleShot(0, download_released.set)
    QTimer.singleShot(0, start)
    with (
        patch.object(manager, "_create_temp_dir", new_temp),
        patch.object(manager, "_download_update_worker", download),
        patch.object(manager, "_normalize_structure", normalize_stage),
        patch.object(manager, "_normalize_extracted_structure", controlled),
        patch.object(Thread, "join", join),
        patch.object(
            update_utils.dialogue,
            "show_warning",
            lambda **kwargs: side_effects.append("warning"),
        ),
        patch.object(
            update_utils.dialogue,
            "show_dialogue_conditional",
            lambda **kwargs: side_effects.append("prompt"),
        ),
        patch.object(
            manager,
            "_launch_update_script",
            lambda *args, **kwargs: side_effects.append("installer"),
        ),
    ):
        try:
            app.exec()
        finally:
            released.set()
    assert download_finished.wait(5)
    assert state == {"completed_at_return": True}, state
    assert side_effects == [], side_effects
    assert manager._progress_widget is not None
    assert not manager._progress_widget.isVisible()
    assert AppInfo().app_storage_folder.is_relative_to(root)
    if not failure:
        assert (source / "RimSort").read_bytes() == b"application"
        assert (source / "data.txt").read_text() == "preserve"
    print(json.dumps(state))


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("before", [False, True], ids=["during", "before-observer"])
def test_application_shutdown_waits_for_normalization(
    tmp_path: Path, failure: bool, before: bool
) -> None:
    code = (
        "import runpy,sys; from pathlib import Path; "
        "module=runpy.run_path(sys.argv[1]); "
        "module['_shutdown_probe'](Path(sys.argv[2]),sys.argv[3]=='1',sys.argv[4]=='1')"
    )
    environment = {
        **os.environ,
        "RIMSORT_DEV": "1",
        "RIMSORT_DEV_DIR": str(tmp_path / "dev"),
        "QT_QPA_PLATFORM": "offscreen",
    }
    environment.pop("APPIMAGE", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(Path(__file__).resolve()),
            str(tmp_path),
            str(int(failure)),
            str(int(before)),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
