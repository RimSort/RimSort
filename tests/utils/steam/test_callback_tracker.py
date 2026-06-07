"""Tests for CallbackTracker -- thread-safe callback completion tracking."""

import threading
import time

from app.utils.steam.steamworks.callback_tracker import CallbackTracker


class TestCallbackTrackerBasic:
    def test_wait_returns_true_when_all_callbacks_received(self) -> None:
        tracker = CallbackTracker(expected=3)
        tracker.record()
        tracker.record()
        tracker.record()
        assert tracker.wait(timeout=1.0) is True
        assert tracker.count == 3

    def test_wait_returns_false_on_timeout(self) -> None:
        tracker = CallbackTracker(expected=3)
        tracker.record()
        assert tracker.wait(timeout=0.1) is False
        assert tracker.count == 1

    def test_cancel_unblocks_wait(self) -> None:
        tracker = CallbackTracker(expected=100)
        unblocked = threading.Event()

        def waiter() -> None:
            tracker.wait(timeout=10.0)
            unblocked.set()

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.05)
        assert not unblocked.is_set()
        tracker.cancel()
        t.join(timeout=1.0)
        assert unblocked.is_set()

    def test_wait_returns_true_instantly_when_already_done(self) -> None:
        tracker = CallbackTracker(expected=1)
        tracker.record()
        start = time.monotonic()
        assert tracker.wait(timeout=5.0) is True
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_is_done_reflects_state(self) -> None:
        tracker = CallbackTracker(expected=1)
        assert tracker.is_done is False
        tracker.record()
        assert tracker.is_done is True


class TestCallbackTrackerEdgeCases:
    def test_expected_zero_is_immediately_done(self) -> None:
        tracker = CallbackTracker(expected=0)
        assert tracker.is_done is True
        assert tracker.wait(timeout=0.1) is True
        assert tracker.count == 0

    def test_expected_none_never_completes_without_cancel(self) -> None:
        tracker = CallbackTracker(expected=None)
        tracker.record()
        tracker.record()
        tracker.record()
        assert tracker.wait(timeout=0.1) is False
        assert tracker.count == 3

    def test_expected_none_completes_with_cancel(self) -> None:
        tracker = CallbackTracker(expected=None)
        tracker.record()
        tracker.cancel()
        assert tracker.wait(timeout=0.1) is True

    def test_extra_records_beyond_expected_do_not_crash(self) -> None:
        tracker = CallbackTracker(expected=1)
        tracker.record()
        tracker.record()
        tracker.record()
        assert tracker.count == 3
        assert tracker.is_done is True


class TestCallbackTrackerConcurrency:
    def test_concurrent_records_are_accurate(self) -> None:
        tracker = CallbackTracker(expected=100)
        barrier = threading.Barrier(10)

        def worker() -> None:
            barrier.wait()
            for _ in range(10):
                tracker.record()

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert tracker.count == 100
        assert tracker.is_done is True
        assert tracker.wait(timeout=0.1) is True

    def test_count_property_is_safe_under_contention(self) -> None:
        tracker = CallbackTracker(expected=1000)
        counts_seen: list[int] = []

        def reader() -> None:
            for _ in range(50):
                counts_seen.append(tracker.count)
                time.sleep(0.001)

        def writer() -> None:
            for _ in range(100):
                tracker.record()
                time.sleep(0.001)

        threads = [threading.Thread(target=reader) for _ in range(5)]
        threads += [threading.Thread(target=writer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert tracker.count == 500
        assert all(isinstance(c, int) and 0 <= c <= 500 for c in counts_seen)
