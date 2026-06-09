"""Tests for MainWindow.closeEvent child window cleanup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtGui import QCloseEvent

from tests.views.conftest import make_stub_main_window


class TestMainWindowCloseEvent:
    """Test that closeEvent closes child windows."""

    @patch("app.views.main_window.MetadataManager")
    def test_close_event_calls_close_child_windows(
        self, mock_mm_cls: MagicMock, qapp: object
    ) -> None:
        """Verify closeEvent delegates to MainContent.close_child_windows."""
        window = make_stub_main_window()

        event = QCloseEvent()
        window.closeEvent(event)

        window.main_content_panel.close_child_windows.assert_called_once()  # type: ignore[attr-defined]

    @patch("app.views.main_window.MetadataManager")
    def test_close_event_stops_watchdog(
        self, mock_mm_cls: MagicMock, qapp: object
    ) -> None:
        """Verify closeEvent stops the watchdog if running."""
        window = make_stub_main_window()
        handler = MagicMock()
        window.watchdog_event_handler = handler

        event = QCloseEvent()
        window.closeEvent(event)

        handler.stop.assert_called_once()
        assert window.watchdog_event_handler is None

    @patch("app.views.main_window.MetadataManager")
    def test_close_event_accepts(self, mock_mm_cls: MagicMock, qapp: object) -> None:
        """Verify closeEvent accepts the event to allow window closure."""
        window = make_stub_main_window()

        event = QCloseEvent()
        window.closeEvent(event)

        assert event.isAccepted()

    @patch("app.views.main_window.MetadataManager")
    def test_close_event_aborts_metadata_refresh(
        self, mock_mm_cls: MagicMock, qapp: object
    ) -> None:
        """Verify closeEvent requests abort on MetadataManager."""
        mock_instance = MagicMock()
        mock_mm_cls.instance.return_value = mock_instance
        window = make_stub_main_window()

        event = QCloseEvent()
        window.closeEvent(event)

        mock_instance.request_abort.assert_called_once()

    @patch("app.views.main_window.MetadataManager")
    def test_close_event_aborts_loading_animation(
        self, mock_mm_cls: MagicMock, qapp: object
    ) -> None:
        """Verify closeEvent calls abort_loading on the content panel."""
        window = make_stub_main_window()

        event = QCloseEvent()
        window.closeEvent(event)

        window.main_content_panel.abort_loading.assert_called_once()  # type: ignore[attr-defined]
