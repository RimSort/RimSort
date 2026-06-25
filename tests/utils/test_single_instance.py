from pathlib import Path

from app.utils.single_instance import SingleInstanceLock


class TestSingleInstanceLock:
    def test_acquire_succeeds_on_first_call(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "rimsort.lock"
        lock = SingleInstanceLock(lock_path)
        assert lock.acquire() is True
        assert lock_path.exists()
        lock.release()

    def test_release_deletes_lock_file(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "rimsort.lock"
        lock = SingleInstanceLock(lock_path)
        lock.acquire()
        lock.release()
        assert not lock_path.exists()

    def test_acquire_fails_when_already_held(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "rimsort.lock"
        lock1 = SingleInstanceLock(lock_path)
        lock2 = SingleInstanceLock(lock_path)
        assert lock1.acquire() is True
        assert lock2.acquire() is False
        lock1.release()

    def test_acquire_recovers_stale_lock(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "rimsort.lock"
        # Write a stale lock file directly (no OS lock backing it)
        lock_path.write_text("99999999\nfakehost\nfakeapp")
        lock = SingleInstanceLock(lock_path)
        assert lock.acquire() is True
        lock.release()

    def test_release_is_safe_when_not_acquired(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "rimsort.lock"
        lock = SingleInstanceLock(lock_path)
        # Should not raise
        lock.release()
