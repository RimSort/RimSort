"""Tests for MainWindow.closeEvent child window cleanup."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtGui import QCloseEvent

from tests.views.conftest import make_stub_main_window


class TestMainWindowCloseEvent:
    """Test that closeEvent closes child windows."""

    def test_close_event_calls_close_child_windows(self, qapp: object) -> None:
        """Verify closeEvent delegates to MainContent.close_child_windows."""
        window = make_stub_main_window()

        event = QCloseEvent()
        window.closeEvent(event)

        window.main_content_panel.close_child_windows.assert_called_once()  # type: ignore[attr-defined]

    def test_close_event_stops_watchdog(self, qapp: object) -> None:
        """Verify closeEvent stops the watchdog if running."""
        window = make_stub_main_window()
        handler = MagicMock()
        window.watchdog_event_handler = handler

        event = QCloseEvent()
        window.closeEvent(event)

        handler.stop.assert_called_once()
        assert window.watchdog_event_handler is None

    def test_close_event_accepts(self, qapp: object) -> None:
        """Verify closeEvent accepts the event to allow window closure."""
        window = make_stub_main_window()

        event = QCloseEvent()
        window.closeEvent(event)

        assert event.isAccepted()
