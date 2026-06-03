from pathlib import Path

from app.utils.log_setup import (
    _anonymize_path,
    _obfuscate_message,
    _rotate_session_logs,
)


def test_anonymize_path_windows() -> None:
    assert (
        _anonymize_path(r"C:\Users\john\Documents\file.txt")
        == r"C:\Users\...\Documents\file.txt"
    )
    assert (
        _anonymize_path(r"D:\Users\abc\Documents\file.txt")
        == r"D:\Users\...\Documents\file.txt"
    )


def test_anonymize_path_linux() -> None:
    assert (
        _anonymize_path("/home/john/Documents/file.txt")
        == "/home/.../Documents/file.txt"
    )
    assert (
        _anonymize_path("/home/abc/Documents/file.txt")
        == "/home/.../Documents/file.txt"
    )


def test_anonymize_path_macos() -> None:
    assert (
        _anonymize_path("/Users/john/Documents/file.txt")
        == "/Users/.../Documents/file.txt"
    )
    assert (
        _anonymize_path("/Users/abc/Documents/file.txt")
        == "/Users/.../Documents/file.txt"
    )


def test_anonymize_path_windows_in_message() -> None:
    assert (
        _anonymize_path(r"Error at: C:\Users\john\file.txt")
        == r"Error at: C:\Users\...\file.txt"
    )


def test_anonymize_path_linux_in_message() -> None:
    assert (
        _anonymize_path("Error at: /home/john/file.txt")
        == "Error at: /home/.../file.txt"
    )


def test_anonymize_path_macos_in_message() -> None:
    assert (
        _anonymize_path("Error at: /Users/john/file.txt")
        == "Error at: /Users/.../file.txt"
    )


def test_anonymize_path_no_path() -> None:
    assert _anonymize_path("no path here") == "no path here"


def test_obfuscate_message_delegates_to_anonymize_path() -> None:
    assert _obfuscate_message("/home/john/file.txt") == "/home/.../file.txt"


def test_obfuscate_message_skip_anonymize() -> None:
    assert (
        _obfuscate_message("/home/john/file.txt", anonymize_path=False)
        == "/home/john/file.txt"
    )


def test_rotate_no_existing_logs(tmp_path: Path) -> None:
    """Rotation is a no-op when no logs exist."""
    _rotate_session_logs(tmp_path, "RimSort.log")
    assert list(tmp_path.iterdir()) == []


def test_rotate_current_becomes_1(tmp_path: Path) -> None:
    """Current log file becomes .1.log."""
    current = tmp_path / "RimSort.log"
    current.write_text("session A")
    _rotate_session_logs(tmp_path, "RimSort.log")
    assert not current.exists()
    assert (tmp_path / "RimSort.1.log").read_text() == "session A"


def test_rotate_cascade(tmp_path: Path) -> None:
    """Existing numbered logs cascade upward."""
    (tmp_path / "RimSort.log").write_text("session C")
    (tmp_path / "RimSort.1.log").write_text("session B")
    (tmp_path / "RimSort.2.log").write_text("session A")
    _rotate_session_logs(tmp_path, "RimSort.log")
    assert (tmp_path / "RimSort.1.log").read_text() == "session C"
    assert (tmp_path / "RimSort.2.log").read_text() == "session B"
    assert (tmp_path / "RimSort.3.log").read_text() == "session A"


def test_rotate_overflow_deleted(tmp_path: Path) -> None:
    """Logs beyond session_history (5) are deleted."""
    (tmp_path / "RimSort.log").write_text("current")
    for i in range(1, 6):
        (tmp_path / f"RimSort.{i}.log").write_text(f"session {i}")
    _rotate_session_logs(tmp_path, "RimSort.log")
    assert not (tmp_path / "RimSort.5.log").exists()
    assert not (tmp_path / "RimSort.6.log").exists()
    assert (tmp_path / "RimSort.1.log").read_text() == "current"
    assert (tmp_path / "RimSort.4.log").exists()


def test_rotate_legacy_old_log_migrated(tmp_path: Path) -> None:
    """Legacy .old.log file is migrated into the numbered scheme."""
    (tmp_path / "RimSort.log").write_text("current")
    (tmp_path / "RimSort.old.log").write_text("legacy")
    _rotate_session_logs(tmp_path, "RimSort.log")
    assert not (tmp_path / "RimSort.old.log").exists()
    assert (tmp_path / "RimSort.1.log").read_text() == "current"
    assert (tmp_path / "RimSort.2.log").read_text() == "legacy"


def test_rotate_legacy_old_log_deleted_when_full(tmp_path: Path) -> None:
    """Legacy .old.log is deleted when all rotation slots are occupied."""
    (tmp_path / "RimSort.log").write_text("current")
    for i in range(1, 5):
        (tmp_path / f"RimSort.{i}.log").write_text(f"session {i}")
    (tmp_path / "RimSort.old.log").write_text("legacy")
    _rotate_session_logs(tmp_path, "RimSort.log")
    assert not (tmp_path / "RimSort.old.log").exists()
