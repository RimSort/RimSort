"""Tests for MainWindow.closeEvent child window cleanup."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtGui import QCloseEvent

from tests.views.conftest import make_stub_main_window


class TestMainWindowCloseEvent:
    """Test that closeEvent closes child windows."""

    def test_close_event_calls_close_child_windows(
        self,
        qapp: object,
        mock_metadata_controller: MagicMock,
    ) -> None:
        """Verify closeEvent delegates to MainContent.close_child_windows."""
        window = make_stub_main_window(mock_metadata_controller)

        event = QCloseEvent()
        window.closeEvent(event)

        window.main_content_panel.close_child_windows.assert_called_once()  # type: ignore[attr-defined]

    def test_close_event_stops_watchdog(
        self,
        qapp: object,
        mock_metadata_controller: MagicMock,
    ) -> None:
        """Verify closeEvent stops the watchdog if running."""
        window = make_stub_main_window(mock_metadata_controller)
        mock_handler = MagicMock()
        window.watchdog_event_handler = mock_handler

        event = QCloseEvent()
        window.closeEvent(event)

        mock_handler.stop.assert_called_once()

    def test_close_event_ignores_none_watchdog(
        self,
        qapp: object,
        mock_metadata_controller: MagicMock,
    ) -> None:
        """No crash when watchdog_event_handler is None."""
        window = make_stub_main_window(mock_metadata_controller)
        assert window.watchdog_event_handler is None

        event = QCloseEvent()
        window.closeEvent(event)

    def test_close_event_aborts_metadata(
        self,
        qapp: object,
        mock_metadata_controller: MagicMock,
    ) -> None:
        """Verify closeEvent requests metadata abort."""
        window = make_stub_main_window(mock_metadata_controller)

        event = QCloseEvent()
        window.closeEvent(event)

        # metadata_controller.is_abort_requested should be set to True
        assert mock_metadata_controller.is_abort_requested is True

    def test_close_event_calls_abort_loading(
        self,
        qapp: object,
        mock_metadata_controller: MagicMock,
    ) -> None:
        """Verify closeEvent calls abort_loading on the main content panel."""
        window = make_stub_main_window(mock_metadata_controller)

        event = QCloseEvent()
        window.closeEvent(event)

        window.main_content_panel.abort_loading.assert_called_once()  # type: ignore[attr-defined]
