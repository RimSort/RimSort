"""Tests for MainWindow.closeEvent child window cleanup."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow

# Ensure steamworks module is mockable for import chain
if "steamworks" not in sys.modules:
    sys.modules["steamworks"] = ModuleType("steamworks")
    sys.modules["steamworks"].STEAMWORKS = MagicMock()  # type: ignore[attr-defined]

if TYPE_CHECKING:
    from app.views.main_window import MainWindow


def _make_stub_main_window() -> MainWindow:
    """Create a MainWindow instance without running MainWindow.__init__.

    We call QMainWindow.__init__ to satisfy the C++ side (Shiboken),
    then attach the minimal attributes that closeEvent expects.
    """
    from app.views.main_window import MainWindow

    instance = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(instance)

    # Attach attributes closeEvent relies on
    instance.main_content_panel = MagicMock()
    instance.watchdog_event_handler = None
    instance.stop_watchdog_if_running = MagicMock()  # type: ignore[method-assign]
    instance.player_log_widget = MagicMock()

    return instance


class TestMainWindowCloseEvent:
    """Test that closeEvent closes child windows."""

    def test_close_event_calls_close_child_windows(self, qapp: object) -> None:
        """Verify closeEvent delegates to MainContent.close_child_windows."""
        window = _make_stub_main_window()

        event = QCloseEvent()
        window.closeEvent(event)

        window.main_content_panel.close_child_windows.assert_called_once()  # type: ignore[attr-defined]

    def test_close_event_stops_watchdog(self, qapp: object) -> None:
        """Verify closeEvent stops the watchdog if running."""
        window = _make_stub_main_window()
        window.watchdog_event_handler = MagicMock()

        event = QCloseEvent()
        window.closeEvent(event)

        window.stop_watchdog_if_running.assert_called_once()  # type: ignore[attr-defined]

    def test_close_event_stops_player_log_monitoring(self, qapp: object) -> None:
        """Verify closeEvent stops player log monitoring if running."""
        window = _make_stub_main_window()

        event = QCloseEvent()
        window.closeEvent(event)

        window.player_log_widget._stop_monitoring.assert_called_once()  # type: ignore[attr-defined]

    def test_close_event_accepts(self, qapp: object) -> None:
        """Verify closeEvent accepts the event to allow window closure."""
        window = _make_stub_main_window()

        event = QCloseEvent()
        window.closeEvent(event)

        assert event.isAccepted()
