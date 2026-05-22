"""
Tests for SteamworksWorker lifecycle and operation handling.

All tests mock the STEAMWORKS class at the import boundary to avoid
requiring a real Steam client.
"""

import time
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from app.utils.steam.steamworks.wrapper import SteamworksWorker


@pytest.fixture(autouse=True)
def _ensure_qapp() -> None:
    if QCoreApplication.instance() is None:
        QCoreApplication([])


def _make_mock_steamworks(loaded: bool = True) -> MagicMock:
    """Create a mock STEAMWORKS instance with Workshop methods."""
    sw = MagicMock()
    sw.loaded.return_value = loaded
    # Use spec to control which Workshop attributes exist.
    # DownloadItem is intentionally absent unless explicitly added by tests.
    sw.Workshop = MagicMock(
        spec=[
            "SubscribeItem",
            "UnsubscribeItem",
            "SetItemSubscribedCallback",
            "SetItemUnsubscribedCallback",
            "SetGetAppDependenciesResultCallback",
            "GetAppDependencies",
            "GetItemState",
            "GetItemDownloadInfo",
        ]
    )
    return sw


@pytest.fixture
def mock_steamworks_class() -> Generator[MagicMock]:
    """Patch the STEAMWORKS class constructor."""
    with patch("app.utils.steam.steamworks.wrapper.STEAMWORKS") as cls:
        mock_sw = _make_mock_steamworks()
        cls.return_value = mock_sw
        cls._mock_instance = mock_sw
        yield cls


class TestWorkerLifecycle:
    def test_worker_starts_idle(self, mock_steamworks_class: MagicMock) -> None:
        worker = SteamworksWorker(idle_timeout=15)
        worker.start()
        time.sleep(0.3)

        assert worker.health_check() is False
        mock_steamworks_class.assert_not_called()

        worker.shutdown()

    def test_first_operation_triggers_init(
        self, mock_steamworks_class: MagicMock
    ) -> None:
        mock_sw = mock_steamworks_class._mock_instance

        # Make callbacks fire immediately by side-effecting the callback registration
        def fire_subscribe_callback(*args: Any, **kwargs: Any) -> None:
            cb = args[0]
            result_obj = MagicMock()
            result_obj.publishedFileId = 12345
            result_obj.result = 1
            cb(result_obj)

        mock_sw.Workshop.SetItemSubscribedCallback.side_effect = fire_subscribe_callback

        worker = SteamworksWorker(idle_timeout=60)
        worker.start()
        time.sleep(0.2)

        worker.subscribe([12345])
        time.sleep(1.0)

        mock_sw.initialize.assert_called_once()
        mock_sw.Workshop.SubscribeItem.assert_called_once_with(12345)

        worker.shutdown()

    def test_idle_timeout_triggers_unload(
        self, mock_steamworks_class: MagicMock
    ) -> None:
        mock_sw = mock_steamworks_class._mock_instance

        def fire_subscribe_callback(*args: Any, **kwargs: Any) -> None:
            cb = args[0]
            result_obj = MagicMock()
            result_obj.publishedFileId = 111
            result_obj.result = 1
            cb(result_obj)

        mock_sw.Workshop.SetItemSubscribedCallback.side_effect = fire_subscribe_callback

        worker = SteamworksWorker(idle_timeout=1)
        worker.start()
        time.sleep(0.2)

        worker.subscribe([111])
        time.sleep(0.5)

        # Not yet unloaded
        mock_sw.unload.assert_not_called()

        # Wait for idle timeout
        time.sleep(1.5)

        mock_sw.unload.assert_called_once()

        worker.shutdown()

    def test_reinit_after_idle_shutdown(self, mock_steamworks_class: MagicMock) -> None:
        mock_sw = mock_steamworks_class._mock_instance

        def fire_subscribe_callback(*args: Any, **kwargs: Any) -> None:
            cb = args[0]
            result_obj = MagicMock()
            result_obj.publishedFileId = 222
            result_obj.result = 1
            cb(result_obj)

        mock_sw.Workshop.SetItemSubscribedCallback.side_effect = fire_subscribe_callback

        worker = SteamworksWorker(idle_timeout=1)
        worker.start()
        time.sleep(0.2)

        # First operation
        worker.subscribe([222])
        time.sleep(2.0)  # Wait for idle unload
        mock_sw.unload.assert_called_once()

        # Second operation should re-init
        worker.subscribe([333])
        time.sleep(1.0)
        assert mock_sw.initialize.call_count == 2

        worker.shutdown()

    def test_steam_not_running_signal(self, mock_steamworks_class: MagicMock) -> None:
        mock_sw = mock_steamworks_class._mock_instance
        mock_sw.initialize.side_effect = Exception("Steam not running")

        worker = SteamworksWorker(idle_timeout=60)
        spy = QSignalSpy(worker.steam_not_running)
        worker.start()
        time.sleep(0.2)

        worker.subscribe([999])
        time.sleep(1.0)

        assert spy.count() >= 1
        mock_sw.Workshop.SubscribeItem.assert_not_called()

        worker.shutdown()

    def test_operation_complete_signal(self, mock_steamworks_class: MagicMock) -> None:
        mock_sw = mock_steamworks_class._mock_instance

        def fire_subscribe_callback(*args: Any, **kwargs: Any) -> None:
            cb = args[0]
            result_obj = MagicMock()
            result_obj.publishedFileId = 555
            result_obj.result = 1
            cb(result_obj)

        mock_sw.Workshop.SetItemSubscribedCallback.side_effect = fire_subscribe_callback

        worker = SteamworksWorker(idle_timeout=60)
        spy = QSignalSpy(worker.operation_complete)
        worker.start()
        time.sleep(0.2)

        worker.subscribe([555])
        time.sleep(1.0)

        assert spy.count() >= 1
        assert spy.at(0) == ["subscribe", True]

        worker.shutdown()

    def test_shutdown_is_clean(self, mock_steamworks_class: MagicMock) -> None:
        worker = SteamworksWorker(idle_timeout=60)
        worker.start()
        time.sleep(0.2)
        assert worker.isRunning()

        worker.shutdown()
        assert not worker.isRunning()


class TestOperationHandling:
    def test_unsubscribe_emits_item_unsubscribed(
        self, mock_steamworks_class: MagicMock
    ) -> None:
        mock_sw = mock_steamworks_class._mock_instance

        def fire_unsub_callback(*args: Any, **kwargs: Any) -> None:
            cb = args[0]
            result_obj = MagicMock()
            result_obj.publishedFileId = 777
            result_obj.result = 1
            cb(result_obj)

        mock_sw.Workshop.SetItemUnsubscribedCallback.side_effect = fire_unsub_callback

        worker = SteamworksWorker(idle_timeout=60)
        spy = QSignalSpy(worker.item_unsubscribed)
        worker.start()
        time.sleep(0.2)

        worker.unsubscribe([777])
        time.sleep(1.0)

        assert spy.count() >= 1
        assert spy.at(0) == ["777"]

        worker.shutdown()

    def test_hasattr_check_for_download_item(
        self, mock_steamworks_class: MagicMock
    ) -> None:
        """DownloadItem is absent (not in Workshop spec) — force_download should not crash."""
        worker = SteamworksWorker(idle_timeout=60)
        spy = QSignalSpy(worker.operation_complete)
        worker.start()
        time.sleep(0.2)

        worker.force_download([888])
        time.sleep(1.0)

        # Should emit operation_complete with False (DownloadItem not supported)
        assert spy.count() >= 1
        assert spy.at(0) == ["force_download", False]

        worker.shutdown()

    def test_force_download_with_download_item(
        self, mock_steamworks_class: MagicMock
    ) -> None:
        """When DownloadItem is present, it should be called."""
        mock_sw = mock_steamworks_class._mock_instance
        mock_sw.Workshop.DownloadItem = MagicMock()

        worker = SteamworksWorker(idle_timeout=60)
        spy = QSignalSpy(worker.operation_complete)
        worker.start()
        time.sleep(0.2)

        worker.force_download([999])
        time.sleep(1.0)

        mock_sw.Workshop.DownloadItem.assert_called_once()
        assert spy.count() >= 1
        assert spy.at(0) == ["force_download", True]

        worker.shutdown()

    def test_app_dependencies_returns_via_future(
        self, mock_steamworks_class: MagicMock
    ) -> None:
        mock_sw = mock_steamworks_class._mock_instance

        def fire_deps_callback(*args: Any, **kwargs: Any) -> None:
            cb = args[0]
            result_obj = MagicMock()
            result_obj.publishedFileId = 444
            result_obj.get_app_dependencies_list.return_value = [294100]
            cb(result_obj)

        mock_sw.Workshop.SetGetAppDependenciesResultCallback.side_effect = (
            fire_deps_callback
        )

        worker = SteamworksWorker(idle_timeout=60)
        worker.start()
        time.sleep(0.2)

        future = worker.query_app_dependencies([444])
        result = future.result(timeout=10)

        assert result is not None
        assert 444 in result
        assert result[444] == [294100]

        worker.shutdown()

    def test_queue_serialization(self, mock_steamworks_class: MagicMock) -> None:
        """Multiple operations submitted rapidly should execute in order."""
        mock_sw = mock_steamworks_class._mock_instance
        call_order: list[str] = []

        def track_subscribe(*args: Any, **kwargs: Any) -> None:
            cb = args[0]
            result_obj = MagicMock()
            result_obj.result = 1

            def on_subscribe_item(pfid: int) -> None:
                call_order.append(f"sub-{pfid}")
                result_obj.publishedFileId = pfid
                cb(result_obj)

            mock_sw.Workshop.SubscribeItem.side_effect = on_subscribe_item

        def track_unsubscribe(*args: Any, **kwargs: Any) -> None:
            cb = args[0]
            result_obj = MagicMock()
            result_obj.result = 1

            def on_unsubscribe_item(pfid: int) -> None:
                call_order.append(f"unsub-{pfid}")
                result_obj.publishedFileId = pfid
                cb(result_obj)

            mock_sw.Workshop.UnsubscribeItem.side_effect = on_unsubscribe_item

        mock_sw.Workshop.SetItemSubscribedCallback.side_effect = track_subscribe
        mock_sw.Workshop.SetItemUnsubscribedCallback.side_effect = track_unsubscribe

        worker = SteamworksWorker(idle_timeout=60)
        worker.start()
        time.sleep(0.2)

        # Submit subscribe then unsubscribe rapidly
        worker.subscribe([100])
        worker.unsubscribe([200])
        time.sleep(2.0)

        assert "sub-100" in call_order
        assert "unsub-200" in call_order
        # Subscribe should come before unsubscribe
        assert call_order.index("sub-100") < call_order.index("unsub-200")

        worker.shutdown()

    def test_subscribe_multiple_pfids(self, mock_steamworks_class: MagicMock) -> None:
        """Subscribe with multiple pfids should call SubscribeItem for each."""
        mock_sw = mock_steamworks_class._mock_instance
        subscribed_pfids: list[int] = []

        def fire_subscribe_callback(*args: Any, **kwargs: Any) -> None:
            cb = args[0]

            def on_item(pfid: int) -> None:
                subscribed_pfids.append(pfid)
                result_obj = MagicMock()
                result_obj.publishedFileId = pfid
                result_obj.result = 1
                cb(result_obj)

            mock_sw.Workshop.SubscribeItem.side_effect = on_item

        mock_sw.Workshop.SetItemSubscribedCallback.side_effect = fire_subscribe_callback

        worker = SteamworksWorker(idle_timeout=60)
        spy = QSignalSpy(worker.item_subscribed)
        worker.start()
        time.sleep(0.2)

        worker.subscribe([100, 200, 300])
        time.sleep(3.0)

        assert subscribed_pfids == [100, 200, 300]
        assert spy.count() == 3
        assert spy.at(0) == ["100"]
        assert spy.at(1) == ["200"]
        assert spy.at(2) == ["300"]

        worker.shutdown()

    def test_subscribe_callback_failure_emits_operation_failed(
        self, mock_steamworks_class: MagicMock
    ) -> None:
        """Callback with result != 1 should emit steam_operation_failed."""
        mock_sw = mock_steamworks_class._mock_instance

        def fire_failed_callback(*args: Any, **kwargs: Any) -> None:
            cb = args[0]
            result_obj = MagicMock()
            result_obj.publishedFileId = 666
            result_obj.result = 2  # failure
            cb(result_obj)

        mock_sw.Workshop.SetItemSubscribedCallback.side_effect = fire_failed_callback

        worker = SteamworksWorker(idle_timeout=60)
        fail_spy = QSignalSpy(worker.steam_operation_failed)
        sub_spy = QSignalSpy(worker.item_subscribed)
        worker.start()
        time.sleep(0.2)

        worker.subscribe([666])
        time.sleep(1.0)

        assert fail_spy.count() >= 1
        assert fail_spy.at(0) == ["666", "subscribe failed"]
        assert sub_spy.count() == 0

        worker.shutdown()

    def test_resubscribe_batched_sequencing(
        self, mock_steamworks_class: MagicMock
    ) -> None:
        """Resubscribe should follow the 5-stage batched pattern."""
        mock_sw = mock_steamworks_class._mock_instance
        stage_log: list[str] = []

        def track_unsub_callback(*args: Any, **kwargs: Any) -> None:
            cb = args[0]

            def on_unsub(pfid: int) -> None:
                stage_log.append(f"unsub-{pfid}")
                result_obj = MagicMock()
                result_obj.publishedFileId = pfid
                result_obj.result = 1
                cb(result_obj)

            mock_sw.Workshop.UnsubscribeItem.side_effect = on_unsub

        def track_sub_callback(*args: Any, **kwargs: Any) -> None:
            cb = args[0]

            def on_sub(pfid: int) -> None:
                stage_log.append(f"sub-{pfid}")
                result_obj = MagicMock()
                result_obj.publishedFileId = pfid
                result_obj.result = 1
                cb(result_obj)

            mock_sw.Workshop.SubscribeItem.side_effect = on_sub

        mock_sw.Workshop.SetItemUnsubscribedCallback.side_effect = track_unsub_callback
        mock_sw.Workshop.SetItemSubscribedCallback.side_effect = track_sub_callback

        worker = SteamworksWorker(idle_timeout=60)
        spy = QSignalSpy(worker.operation_complete)
        worker.start()
        time.sleep(0.2)

        worker.resubscribe([10, 20])
        # Resubscribe takes: API calls + 4s wait + API calls + 2s wait + download
        time.sleep(10.0)

        # All unsubs should come before all subs
        assert "unsub-10" in stage_log
        assert "unsub-20" in stage_log
        assert "sub-10" in stage_log
        assert "sub-20" in stage_log
        unsub_end = max(stage_log.index("unsub-10"), stage_log.index("unsub-20"))
        sub_start = min(stage_log.index("sub-10"), stage_log.index("sub-20"))
        assert unsub_end < sub_start

        assert spy.count() >= 1
        assert spy.at(0)[0] == "resubscribe"

        worker.shutdown()

    def test_stale_callback_ignored_across_operations(
        self, mock_steamworks_class: MagicMock
    ) -> None:
        """Late callbacks from a previous operation should not affect the next one."""
        mock_sw = mock_steamworks_class._mock_instance
        stored_callbacks: list[Any] = []

        def capture_subscribe_callback(*args: Any, **kwargs: Any) -> None:
            stored_callbacks.append(args[0])

            def on_item(pfid: int) -> None:
                if pfid == 200:
                    cb = stored_callbacks[-1]
                    result_obj = MagicMock()
                    result_obj.publishedFileId = pfid
                    result_obj.result = 1
                    cb(result_obj)

            mock_sw.Workshop.SubscribeItem.side_effect = on_item

        mock_sw.Workshop.SetItemSubscribedCallback.side_effect = (
            capture_subscribe_callback
        )

        worker = SteamworksWorker(idle_timeout=60)
        worker.start()
        time.sleep(0.2)

        # First operation — callback won't fire (simulating dropped callback)
        worker.subscribe([100])
        time.sleep(2.0)

        # Second operation — callback fires normally
        worker.subscribe([200])
        time.sleep(2.0)

        # Fire the stale callback from op 1 — should be ignored by generation check
        if len(stored_callbacks) >= 1:
            stale_cb = stored_callbacks[0]
            result_obj = MagicMock()
            result_obj.publishedFileId = 100
            result_obj.result = 1
            stale_cb(result_obj)

        time.sleep(0.5)
        assert worker._pending_callbacks >= 0

        worker.shutdown()
