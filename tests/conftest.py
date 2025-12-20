from typing import Generator, Union

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDialog


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
