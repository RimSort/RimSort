"""Thread-safe callback completion tracker for Steamworks async operations."""

import threading


class CallbackTracker:
    """
    Tracks callback completion for batched Steamworks operations.

    Uses threading.Event for zero-latency completion signaling and
    threading.Lock for safe concurrent access to the counter.
    """

    def __init__(self, expected: int | None = None) -> None:
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._count = 0
        self._expected = expected
        if expected is not None and expected <= 0:
            self._done.set()

    def record(self) -> None:
        """Record a callback completion. Thread-safe."""
        with self._lock:
            self._count += 1
            if self._expected is not None and self._count >= self._expected:
                self._done.set()

    def wait(self, timeout: float) -> bool:
        """
        Block until all expected callbacks are received or timeout expires.

        :param timeout: Maximum seconds to wait.
        :return: True if all callbacks completed, False on timeout.
        """
        return self._done.wait(timeout=timeout)

    def cancel(self) -> None:
        """Unblock any threads waiting on this tracker."""
        self._done.set()

    @property
    def count(self) -> int:
        """Return the number of callbacks recorded so far. Thread-safe."""
        with self._lock:
            return self._count

    @property
    def is_done(self) -> bool:
        """Return True if all expected callbacks have been received or cancelled."""
        return self._done.is_set()
