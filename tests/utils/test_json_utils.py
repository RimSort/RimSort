import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils.json_utils import _clear_read_only_flag, atomic_json_dump


def test_atomic_json_dump_retries_transient_replace_permission_error(
    tmp_path: Path,
) -> None:
    target = tmp_path / "settings.json"
    real_replace = os.replace
    attempts = 0

    def flaky_replace(source: str, destination: str) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("temporarily locked")
        real_replace(source, destination)

    with (
        patch("app.utils.json_utils.os.replace", side_effect=flaky_replace),
        patch("app.utils.json_utils.time.sleep") as sleep,
    ):
        atomic_json_dump({"language": "en"}, str(target))

    assert attempts == 2
    sleep.assert_called_once_with(0.05)
    assert json.loads(target.read_text(encoding="utf-8")) == {"language": "en"}


def test_atomic_json_dump_cleans_temp_file_after_persistent_permission_error(
    tmp_path: Path,
) -> None:
    target = tmp_path / "settings.json"

    with (
        patch(
            "app.utils.json_utils.os.replace",
            side_effect=PermissionError("still locked"),
        ),
        patch("app.utils.json_utils.time.sleep") as sleep,
        pytest.raises(PermissionError, match="still locked"),
    ):
        atomic_json_dump({"language": "en"}, str(target))

    assert list(tmp_path.iterdir()) == []
    assert sleep.call_count == 4


def test_clear_read_only_flag_is_a_no_op_off_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POSIX replaces do not depend on the read-only attribute."""
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, stat.S_IREAD)
    monkeypatch.setattr(sys, "platform", "linux")

    assert _clear_read_only_flag(str(target)) is False
    assert (os.stat(target).st_mode & stat.S_IWRITE) == 0


def test_clear_read_only_flag_ignores_missing_and_writable_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only read-only files that exist are cleared."""
    writable = tmp_path / "writable.json"
    writable.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "platform", "win32")

    assert _clear_read_only_flag(str(writable)) is False
    assert _clear_read_only_flag(str(tmp_path / "missing.json")) is False


@pytest.mark.skipif(
    sys.platform != "win32", reason="Read-only file attribute is Windows-only"
)
def test_clear_read_only_flag_clears_the_attribute_once(tmp_path: Path) -> None:
    """Clearing the attribute is reported once, so the change stays visible."""
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, stat.S_IREAD)

    with patch("app.utils.json_utils.logger") as mock_logger:
        assert _clear_read_only_flag(str(target)) is True
        assert _clear_read_only_flag(str(target)) is False

    mock_logger.warning.assert_called_once()
    assert (os.stat(target).st_mode & stat.S_IWRITE) != 0


def test_atomic_json_dump_keeps_retry_budget_after_clearing_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clearing the read-only attribute must not consume a lock retry."""
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, stat.S_IREAD)
    monkeypatch.setattr(sys, "platform", "win32")

    with (
        patch(
            "app.utils.json_utils.os.replace",
            side_effect=PermissionError("still locked"),
        ),
        patch("app.utils.json_utils.time.sleep") as sleep,
        pytest.raises(PermissionError, match="still locked"),
    ):
        atomic_json_dump({"language": "en"}, str(target))

    assert (os.stat(target).st_mode & stat.S_IWRITE) != 0
    assert sleep.call_count == 4


@pytest.mark.skipif(
    sys.platform != "win32", reason="Read-only file attribute is Windows-only"
)
def test_atomic_json_dump_replaces_read_only_destination(tmp_path: Path) -> None:
    """A read-only destination must not block saving (issue #2317)."""
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, stat.S_IREAD)

    atomic_json_dump({"language": "en"}, str(target))

    assert json.loads(target.read_text(encoding="utf-8")) == {"language": "en"}
