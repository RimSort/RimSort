import subprocess
from typing import Any, Generator, Union
from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDialog

_real_popen = subprocess.Popen


@pytest.fixture(autouse=True)
def _block_steam_urls(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Prevent tests from opening steam:// URLs on the host machine.

    Guards subprocess.Popen to block any steam:// URI regardless of
    which Python function initiated the call. This catches cases where
    platform_specific_open is patched at the wrong import location.
    """

    def _guarded_popen(*args: Any, **kw: Any) -> subprocess.Popen[Any]:
        popen_args = args[0] if args else kw.get("args", "")
        cmd_str = (
            " ".join(str(x) for x in popen_args)
            if isinstance(popen_args, (list, tuple))
            else str(popen_args)
        )
        if "steam://" in cmd_str:
            raise RuntimeError(
                f"Test {request.node.nodeid} tried to open a steam:// URL "
                f"via subprocess: {cmd_str}"
            )
        return _real_popen(*args, **kw)

    with patch.object(subprocess, "Popen", _guarded_popen):
        yield


@pytest.fixture(autouse=True)
def auto_accept_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Automatically accept all QDialog exec_ calls during tests to prevent blocking.
    """

    def fake_exec(self: QDialog) -> int:
        # Return QDialog.Accepted constant value 1
        return 1

    monkeypatch.setattr(QDialog, "exec_", fake_exec)
    monkeypatch.setattr(QDialog, "exec", fake_exec)


@pytest.fixture(scope="function")
def qapp() -> Generator[Union[QApplication, QCoreApplication], None, None]:
    """Create a QApplication instance for Qt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
