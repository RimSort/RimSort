"""AppImage recovery survives startup until the main GUI loop is ready."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QMainWindow
from pytestqt.qtbot import QtBot

from app.controllers.app_controller import AppController

_STARTUP_PROBE = """
import os
import sys
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow

root, mode = Path(sys.argv[1]), sys.argv[2]
image = root / 'RimSort.AppImage'
backup = root / 'RimSort.AppImage.bak'
image.write_bytes(b'new application')
if mode != 'no-backup':
    backup.write_bytes(b'working application')
if mode == 'non-appimage':
    os.environ.pop('APPIMAGE', None)
else:
    os.environ['APPIMAGE'] = str(image)

from app.controllers.app_controller import AppController
from app.utils.app_info import AppInfo

def check_preserved() -> None:
    assert image.read_bytes() == b'new application'
    if mode == 'no-backup':
        assert not backup.exists()
    else:
        assert backup.read_bytes() == b'working application'

AppInfo()
check_preserved()
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
initialized = []
finished = []
removal_attempts = []
unlink = Path.unlink

def fail_unlink(path: Path, missing_ok: bool = False) -> None:
    if path == backup:
        removal_attempts.append(True)
        raise PermissionError('Controlled backup cleanup failure')
    unlink(path, missing_ok=missing_ok)

if mode == 'unlink-error':
    Path.unlink = fail_unlink

class Window(QMainWindow):
    def initialize_content(self, is_initial: bool = True) -> None:
        assert is_initial
        check_preserved()
        nested = QEventLoop()
        QTimer.singleShot(0, nested.quit)
        nested.exec()
        check_preserved()
        if mode == 'init-error':
            raise RuntimeError('Controlled startup failure')
        if mode == 'init-close':
            self.close()
        initialized.append(True)

window = Window()
controller = AppController.__new__(AppController)
QObject.__init__(controller)
controller.main_window = window

def finish() -> None:
    finished.append(True)
    app.quit()

class Loop:
    def exec(self) -> int:
        check_preserved()
        assert initialized
        if mode == 'loop-error':
            raise RuntimeError('Controlled event-loop failure')
        if mode == 'loop-not-entered':
            return 0
        if mode == 'hidden-before-loop':
            window.hide()
        QTimer.singleShot(50, finish)
        return app.exec()

controller.app = Loop()
try:
    result = controller.run()
    assert result == 0
    assert mode not in {'init-error', 'loop-error'}
except RuntimeError as error:
    assert mode in {'init-error', 'loop-error'}, str(error)
    assert 'Controlled' in str(error)
finally:
    Path.unlink = unlink

# A stopped startup timer must not delete the backup in a later event loop.
app.processEvents()
assert image.read_bytes() == b'new application'
if mode in {'ready', 'no-backup'}:
    assert finished
    assert not backup.exists()
else:
    check_preserved()
if mode == 'unlink-error':
    assert removal_attempts == [True]
window.close()
print('APPIMAGE_STARTUP_OK', mode)
"""


@pytest.mark.parametrize(
    "mode",
    [
        "ready",
        "init-error",
        "init-close",
        "loop-error",
        "loop-not-entered",
        "hidden-before-loop",
        "unlink-error",
        "non-appimage",
        "no-backup",
    ],
)
def test_appimage_backup_startup_boundary(tmp_path: Path, mode: str) -> None:
    environment = {
        **os.environ,
        "RIMSORT_DEV": "1",
        "RIMSORT_DEV_DIR": str(tmp_path / "profile"),
        "QT_QPA_PLATFORM": "offscreen",
    }
    result = subprocess.run(
        [sys.executable, "-c", _STARTUP_PROBE, str(tmp_path), mode],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"APPIMAGE_STARTUP_OK {mode}" in result.stdout


@pytest.mark.parametrize("cleanup_failure", [False, True])
def test_gui_startup_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    cleanup_failure: bool,
) -> None:
    image = tmp_path / "RimSort.AppImage"
    image.write_bytes(b"new application")
    backup = image.with_suffix(".AppImage.bak")
    backup.write_bytes(b"working application")
    monkeypatch.setenv("APPIMAGE", str(image))
    window = QMainWindow()
    qtbot.addWidget(window)
    controller = AppController.__new__(AppController)
    QObject.__init__(controller)
    controller.main_window = MagicMock(wraps=window)
    controller.app = MagicMock(spec=QApplication)
    attempts: list[Path] = []
    unlink = Path.unlink

    def remove(path: Path, missing_ok: bool = False) -> None:
        if path == backup:
            attempts.append(path)
            if cleanup_failure:
                raise PermissionError("Controlled backup cleanup failure")
        unlink(path, missing_ok=missing_ok)

    def initialize_content(is_initial: bool) -> None:
        assert is_initial
        QApplication.processEvents()
        assert backup.read_bytes() == b"working application"

    def enter_loop() -> int:
        assert backup.read_bytes() == b"working application"
        qtbot.waitUntil(lambda: bool(attempts))
        return 0

    monkeypatch.setattr(Path, "unlink", remove)
    controller.main_window.initialize_content = initialize_content
    controller.app.exec.side_effect = enter_loop

    assert controller.run() == 0
    assert attempts == [backup]
    assert image.read_bytes() == b"new application"
    if cleanup_failure:
        assert backup.read_bytes() == b"working application"
    else:
        assert not backup.exists()
