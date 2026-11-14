"""The update indicator is persistent, clickable, and independent of status text."""

from pathlib import Path
from threading import Thread, get_ident
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMainWindow
from pytestqt.qtbot import QtBot

from app.models.settings import Settings
from app.utils.event_bus import EventBus
from app.views.main_window import MainWindow
from app.views.status_panel import Status


class _NotificationWindow(MainWindow):
    def __init__(self, settings: Settings, prefix: Path) -> None:
        QMainWindow.__init__(self)
        self.settings = settings
        self.bottom_panel = Status()
        self.setCentralWidget(self.bottom_panel.frame)
        self.main_content_panel = MagicMock()
        self.main_content_controller = MagicMock()
        self.metadata_controller = MagicMock()
        self.menu_bar_controller = MagicMock()
        self.steamcmd_wrapper = MagicMock(steamcmd_prefix=str(prefix))
        self.watchdog_event_handler = None
        self._get_active_instance = lambda: settings.instances[
            settings.current_instance
        ]
        self._initialize_application_update_notification()


@pytest.fixture
def window(
    mock_settings_controller: MagicMock,
    tmp_path: Path,
    qtbot: QtBot,
) -> _NotificationWindow:
    settings = mock_settings_controller.settings
    settings.watchdog_toggle = False
    settings.instances[settings.current_instance].initial_setup = False
    result = _NotificationWindow(settings, tmp_path)
    qtbot.addWidget(result)
    result.show()
    return result


def test_indicator_shows_release_and_click_uses_manual_check(
    window: _NotificationWindow, qtbot: QtBot
) -> None:
    button = window.bottom_panel.update_available_button
    assert button.isHidden()

    window._startup_update_manager.update_available.emit("v1.1.0")

    assert button.isVisible()
    assert button.text() == "Update available"
    assert "v1.1.0" in button.toolTip()
    window.bottom_panel.actions_slot("refresh")
    assert button.isVisible()
    with qtbot.waitSignal(EventBus().do_check_for_application_update):
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)

    window._startup_update_manager.update_available.emit("")
    assert button.isHidden()


@pytest.mark.parametrize(
    ("initial", "enabled", "expected"),
    [(True, True, 1), (True, False, 0), (False, True, 0)],
)
def test_startup_uses_quiet_check_only_once_per_launch(
    window: _NotificationWindow,
    monkeypatch: pytest.MonkeyPatch,
    initial: bool,
    enabled: bool,
    expected: int,
) -> None:
    window.settings.check_for_update_startup = enabled
    quiet = MagicMock()
    monkeypatch.setattr(
        window._startup_update_manager, "_check_for_update_silently", quiet
    )
    interactive: list[bool] = []
    EventBus().do_check_for_application_update.connect(lambda: interactive.append(True))

    window.initialize_content(is_initial=initial)

    assert quiet.call_count == expected
    assert interactive == []


def test_worker_notification_updates_widgets_on_gui_thread(
    window: _NotificationWindow, monkeypatch: pytest.MonkeyPatch, qtbot: QtBot
) -> None:
    button = window.bottom_panel.update_available_button
    set_visible = button.setVisible
    callback_threads: list[int] = []

    def record(visible: bool) -> None:
        callback_threads.append(get_ident())
        set_visible(visible)

    monkeypatch.setattr(button, "setVisible", record)
    worker = Thread(
        target=window._startup_update_manager.update_available.emit,
        args=("v1.1.0",),
        daemon=True,
    )
    worker.start()
    qtbot.waitUntil(button.isVisible)
    worker.join(timeout=1)

    assert callback_threads == [get_ident()]
