import json
from pathlib import Path

from app.utils.log_config import _rotate_session_logs


def test_rotate_session_logs_no_existing_files(tmp_path: Path) -> None:
    """Rotation with no existing logs should be a no-op."""
    _rotate_session_logs(tmp_path, "RimSort.log", session_history=5)
    assert list(tmp_path.iterdir()) == []


def test_rotate_session_logs_single_existing(tmp_path: Path) -> None:
    """Existing RimSort.log should become RimSort.1.log."""
    (tmp_path / "RimSort.log").write_text("session 0")
    _rotate_session_logs(tmp_path, "RimSort.log", session_history=5)
    assert not (tmp_path / "RimSort.log").exists()
    assert (tmp_path / "RimSort.1.log").read_text() == "session 0"


def test_rotate_session_logs_cascade(tmp_path: Path) -> None:
    """Multiple existing logs cascade upward."""
    (tmp_path / "RimSort.log").write_text("session 0")
    (tmp_path / "RimSort.1.log").write_text("session 1")
    (tmp_path / "RimSort.2.log").write_text("session 2")
    _rotate_session_logs(tmp_path, "RimSort.log", session_history=5)
    assert not (tmp_path / "RimSort.log").exists()
    assert (tmp_path / "RimSort.1.log").read_text() == "session 0"
    assert (tmp_path / "RimSort.2.log").read_text() == "session 1"
    assert (tmp_path / "RimSort.3.log").read_text() == "session 2"


def test_rotate_session_logs_exceeds_history(tmp_path: Path) -> None:
    """Oldest log beyond history limit is deleted."""
    (tmp_path / "RimSort.log").write_text("session 0")
    (tmp_path / "RimSort.1.log").write_text("session 1")
    (tmp_path / "RimSort.2.log").write_text("session 2")
    _rotate_session_logs(tmp_path, "RimSort.log", session_history=3)
    assert not (tmp_path / "RimSort.log").exists()
    assert (tmp_path / "RimSort.1.log").read_text() == "session 0"
    assert (tmp_path / "RimSort.2.log").read_text() == "session 1"
    # session 2 was at index 2, pushed to index 3 which equals history limit -> deleted
    assert not (tmp_path / "RimSort.3.log").exists()


def test_rotate_session_logs_migrates_old_format(tmp_path: Path) -> None:
    """Legacy RimSort.old.log is migrated to RimSort.1.log."""
    (tmp_path / "RimSort.log").write_text("current")
    (tmp_path / "RimSort.old.log").write_text("old")
    _rotate_session_logs(tmp_path, "RimSort.log", session_history=5)
    assert not (tmp_path / "RimSort.old.log").exists()
    assert (tmp_path / "RimSort.1.log").read_text() == "current"
    assert (tmp_path / "RimSort.2.log").read_text() == "old"
