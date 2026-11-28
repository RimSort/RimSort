"""Tests for WatchdogHandler lifecycle methods."""

from __future__ import annotations

from pathlib import Path
from threading import Timer
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject
from watchdog.events import DirCreatedEvent, DirDeletedEvent, FileModifiedEvent


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


def _configure_event_handler(
    handler: Any, tmp_path: Path, mods_metadata: dict[str, object]
) -> tuple[Path, Path, MagicMock]:
    """Configure only the instance data needed by mod event handlers."""
    local_root = tmp_path / "Mods"
    local_root.mkdir()
    workshop_root = tmp_path / "Workshop"
    workshop_root.mkdir()
    metadata_controller = MagicMock()
    metadata_controller.mods_metadata = mods_metadata
    metadata_controller.resolve_about_xml_to_mod_path.return_value = None
    handler._instance = SimpleNamespace(
        game_folder="",
        local_folder=str(local_root),
        workshop_folder=str(workshop_root),
    )
    handler.metadata_controller = metadata_controller
    handler.workshop_acf_path = None
    handler.steamcmd_appworkshop_acf_path = str(tmp_path / "missing-acf")
    handler._WatchdogHandler__cooldown_mod_change = MagicMock()
    return local_root, workshop_root, metadata_controller


class TestWatchdogHandlerEventFilter:
    """The mod observer subscribes only to events its handler consumes."""

    def test_mod_observers_filter_to_handled_event_types(
        self, qapp: object, tmp_path: Path
    ) -> None:
        handler = _make_handler()
        roots = [tmp_path / name for name in ("Data", "Mods", "Workshop")]
        for root in roots:
            root.mkdir()

        handler._WatchdogHandler__add_mod_observers([str(root) for root in roots])

        calls = handler.watchdog_mods_observer.schedule.call_args_list
        expected_filter = [DirCreatedEvent, DirDeletedEvent, FileModifiedEvent]
        assert len(calls) == len(roots)
        for schedule_call, root in zip(calls, roots, strict=True):
            assert schedule_call.args == (handler, str(root))
            assert schedule_call.kwargs == {
                "recursive": True,
                "event_filter": expected_filter,
            }

    def test_created_mod_directory_still_emits_creation(
        self, qapp: object, tmp_path: Path
    ) -> None:
        handler = _make_handler()
        local_root, _, _ = _configure_event_handler(handler, tmp_path, {})
        new_mod = local_root / "new_mod"
        new_mod.mkdir()

        handler.on_created(DirCreatedEvent(str(new_mod)))

        callback = handler._WatchdogHandler__cooldown_mod_change.call_args.kwargs[
            "callback"
        ]
        assert callback == {
            "operation": "created",
            "data_source": "local",
            "path": str(new_mod),
        }

    def test_deleted_mod_directory_still_emits_deletion(
        self, qapp: object, tmp_path: Path
    ) -> None:
        handler = _make_handler()
        local_root, _, metadata_controller = _configure_event_handler(
            handler, tmp_path, {}
        )
        mod_path = local_root / "existing_mod"
        mod_path.mkdir()
        metadata_controller.mods_metadata[str(mod_path)] = object()

        handler.on_deleted(DirDeletedEvent(str(mod_path)))

        callback = handler._WatchdogHandler__cooldown_mod_change.call_args.kwargs[
            "callback"
        ]
        assert callback == {"operation": "deleted", "path": str(mod_path)}

    @pytest.mark.parametrize(
        ("about_dir", "about_filename"),
        [("About", "About.xml"), ("about", "about.xml")],
    )
    def test_about_xml_modification_still_emits_update(
        self,
        qapp: object,
        tmp_path: Path,
        about_dir: str,
        about_filename: str,
    ) -> None:
        handler = _make_handler()
        local_root, _, metadata_controller = _configure_event_handler(
            handler, tmp_path, {}
        )
        mod_path = local_root / "existing_mod"
        about_xml = mod_path / about_dir / about_filename
        about_xml.parent.mkdir(parents=True)
        about_xml.write_text("<ModMetaData />")
        metadata_controller.mods_metadata[str(mod_path)] = object()
        metadata_controller.resolve_about_xml_to_mod_path.return_value = str(mod_path)

        handler.on_modified(FileModifiedEvent(str(about_xml)))

        callback = handler._WatchdogHandler__cooldown_mod_change.call_args.kwargs[
            "callback"
        ]
        assert callback == {"operation": "updated", "path": str(mod_path)}
        metadata_controller.resolve_about_xml_to_mod_path.assert_called_once_with(
            str(about_xml)
        )


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
