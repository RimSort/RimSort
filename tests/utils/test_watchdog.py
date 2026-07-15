"""Tests for WatchdogHandler lifecycle methods."""

from __future__ import annotations

from threading import Timer
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject


def _make_handler(acf_alive: bool = True, mods_alive: bool = True) -> Any:
    """Create a WatchdogHandler without real observers."""
    from app.utils.watchdog import WatchdogHandler

    handler = WatchdogHandler.__new__(WatchdogHandler)
    QObject.__init__(handler)

    handler.watchdog_acf_observer = MagicMock()
    handler.watchdog_acf_observer.is_alive.return_value = acf_alive
    handler.watchdog_mods_observer = MagicMock()
    handler.watchdog_mods_observer.is_alive.return_value = mods_alive
    handler.cooldown_timers = {
        "t1": MagicMock(spec=Timer),
        "t2": MagicMock(spec=Timer),
    }
    return handler


class TestWatchdogHandlerStop:
    """Tests for WatchdogHandler.stop() method."""

    def test_stop_both_observers_alive(self, qapp: object) -> None:
        """Both observers alive: both must be stopped and joined."""
        handler = _make_handler(acf_alive=True, mods_alive=True)
        acf_obs = handler.watchdog_acf_observer
        mods_obs = handler.watchdog_mods_observer

        handler.stop()

        acf_obs.stop.assert_called_once()
        acf_obs.join.assert_called_once()
        mods_obs.stop.assert_called_once()
        mods_obs.join.assert_called_once()

    def test_stop_only_acf_alive(self, qapp: object) -> None:
        """Only ACF alive: ACF stopped, mods skipped."""
        handler = _make_handler(acf_alive=True, mods_alive=False)
        acf_obs = handler.watchdog_acf_observer
        mods_obs = handler.watchdog_mods_observer

        handler.stop()

        acf_obs.stop.assert_called_once()
        mods_obs.stop.assert_not_called()

    def test_stop_only_mods_alive(self, qapp: object) -> None:
        """Only mods alive: mods stopped, ACF skipped."""
        handler = _make_handler(acf_alive=False, mods_alive=True)
        acf_obs = handler.watchdog_acf_observer
        mods_obs = handler.watchdog_mods_observer

        handler.stop()

        acf_obs.stop.assert_not_called()
        mods_obs.stop.assert_called_once()

    @pytest.mark.parametrize(
        "acf_alive,mods_alive",
        [(True, True), (True, False), (False, True), (False, False)],
    )
    def test_stop_always_cancels_timers(
        self, qapp: object, acf_alive: bool, mods_alive: bool
    ) -> None:
        """Timers must always be cancelled regardless of which observers were alive."""
        handler = _make_handler(acf_alive=acf_alive, mods_alive=mods_alive)
        timers = list(handler.cooldown_timers.values())

        handler.stop()

        for timer in timers:
            timer.cancel.assert_called_once()

    def test_stop_clears_timers_dict(self, qapp: object) -> None:
        """Timers dict must be empty after stop."""
        handler = _make_handler()

        handler.stop()

        assert handler.cooldown_timers == {}

    def test_stop_nulls_observers(self, qapp: object) -> None:
        """Observers must be None after stop."""
        handler = _make_handler()

        handler.stop()

        assert handler.watchdog_acf_observer is None
        assert handler.watchdog_mods_observer is None

    def test_stop_none_observers_is_noop(self, qapp: object) -> None:
        """Calling stop when observers are already None should not raise."""
        handler = _make_handler()
        handler.watchdog_acf_observer = None
        handler.watchdog_mods_observer = None
        handler.cooldown_timers = {}

        handler.stop()  # should not raise

    def test_stop_idempotent(self, qapp: object) -> None:
        """Calling stop twice should not raise."""
        handler = _make_handler()

        handler.stop()
        handler.stop()  # second call is a noop


class TestWatchdogHandlerStart:
    """Tests for WatchdogHandler.start() method."""

    def test_start_both_observers(self, qapp: object) -> None:
        """Both observers present: both must be started."""
        handler = _make_handler(acf_alive=False, mods_alive=False)

        handler.start()

        handler.watchdog_acf_observer.start.assert_called_once()
        handler.watchdog_mods_observer.start.assert_called_once()

    def test_start_skips_already_alive_with_warning(self, qapp: object) -> None:
        """If an observer is already alive, skip it and log a warning."""
        handler = _make_handler(acf_alive=True, mods_alive=True)

        handler.start()  # should not raise

        handler.watchdog_acf_observer.start.assert_not_called()
        handler.watchdog_mods_observer.start.assert_not_called()

    def test_start_none_observers_logs_warning(self, qapp: object) -> None:
        """None observers should log warnings, not crash."""
        handler = _make_handler()
        handler.watchdog_acf_observer = None
        handler.watchdog_mods_observer = None

        handler.start()  # should not raise
