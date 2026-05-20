import json
from pathlib import Path

from loguru import logger

from app.utils.log_config import _rotate_session_logs, setup_logging


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


def test_setup_logging_creates_human_readable_log(tmp_path: Path) -> None:
    """setup_logging creates a human-readable log file and writes to it."""
    setup_logging(log_dir=tmp_path, debug=False, json_logging=False)
    logger.info("test message")
    logger.complete()

    log_file = tmp_path / "RimSort.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "test message" in content
    assert "[INFO]" in content


def test_setup_logging_debug_level(tmp_path: Path) -> None:
    """debug=True enables DEBUG level in the file sink."""
    setup_logging(log_dir=tmp_path, debug=True, json_logging=False)
    logger.debug("debug message")
    logger.complete()

    content = (tmp_path / "RimSort.log").read_text()
    assert "debug message" in content
    assert "[DEBUG]" in content


def test_setup_logging_info_level_filters_debug(tmp_path: Path) -> None:
    """debug=False (INFO level) filters out DEBUG messages."""
    setup_logging(log_dir=tmp_path, debug=False, json_logging=False)
    logger.debug("should not appear")
    logger.info("should appear")
    logger.complete()

    content = (tmp_path / "RimSort.log").read_text()
    assert "should not appear" not in content
    assert "should appear" in content


def test_formatter_obfuscates_paths(tmp_path: Path) -> None:
    """Log messages containing usernames in paths are obfuscated."""
    setup_logging(log_dir=tmp_path, debug=True, json_logging=False)
    logger.info("Loading from /home/johndoe/mods/core")
    logger.info("Loading from /Users/janedoe/mods/core")
    logger.info("Loading from C:\\Users\\player\\mods\\core")
    logger.complete()

    content = (tmp_path / "RimSort.log").read_text()
    assert "johndoe" not in content
    assert "janedoe" not in content
    assert "player" not in content
    assert "/home/.../" in content
    assert "/Users/.../" in content
    assert "\\Users\\...\\" in content


def test_formatter_includes_exception(tmp_path: Path) -> None:
    """logger.exception() includes traceback in output."""
    setup_logging(log_dir=tmp_path, debug=True, json_logging=False)
    try:
        raise ValueError("test error")
    except ValueError:
        logger.exception("caught error")
    logger.complete()

    content = (tmp_path / "RimSort.log").read_text()
    assert "caught error" in content
    assert "ValueError: test error" in content
    assert "Traceback" in content
