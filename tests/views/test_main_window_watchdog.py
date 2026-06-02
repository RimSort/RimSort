"""Tests for MainWindow watchdog delegation."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.views.conftest import make_stub_main_window


class TestShutdownWatchdog:
    def test_delegates_to_handler_stop(self, qapp: object) -> None:
        """shutdown_watchdog must call handler.stop() and clear the reference."""
        window = make_stub_main_window()
        handler = MagicMock()
        window.watchdog_event_handler = handler

        window.shutdown_watchdog()

        handler.stop.assert_called_once()
        assert window.watchdog_event_handler is None

    def test_no_handler_is_noop(self, qapp: object) -> None:
        """Calling shutdown with no handler should not raise."""
        window = make_stub_main_window()
        window.watchdog_event_handler = None

        window.shutdown_watchdog()

        assert window.watchdog_event_handler is None

    def test_stop_if_running_delegates(self, qapp: object) -> None:
        """stop_watchdog_if_running calls shutdown when handler exists."""
        window = make_stub_main_window()
        handler = MagicMock()
        window.watchdog_event_handler = handler

        window.stop_watchdog_if_running()

        handler.stop.assert_called_once()
        assert window.watchdog_event_handler is None

    def test_stop_if_running_noop_when_none(self, qapp: object) -> None:
        """stop_watchdog_if_running is a noop when handler is None."""
        window = make_stub_main_window()
        window.watchdog_event_handler = None

        window.stop_watchdog_if_running()  # should not raise
