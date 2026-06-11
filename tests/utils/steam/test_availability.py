import sys
from unittest.mock import MagicMock, patch

from app.utils.steam.availability import is_steam_running


@patch("psutil.process_iter")
def test_is_steam_running_returns_true_when_steam_process_found(
    mock_process_iter: MagicMock,
) -> None:
    """Test that is_steam_running detects Steam process on current platform."""
    # Use a platform-appropriate Steam process name
    if sys.platform == "win32":
        process_name = "steam.exe"
    elif sys.platform == "darwin":
        process_name = "steam_osx"
    else:
        process_name = "steam"

    mock_process = MagicMock()
    mock_process.info = {"name": process_name}
    mock_process_iter.return_value = [mock_process]
    assert is_steam_running() is True


@patch("psutil.process_iter")
def test_is_steam_running_returns_false_when_no_steam_process(
    mock_process_iter: MagicMock,
) -> None:
    """Test that is_steam_running returns False when no Steam process exists."""
    mock_process = MagicMock()
    mock_process.info = {"name": "firefox"}
    mock_process_iter.return_value = [mock_process]
    assert is_steam_running() is False


@patch("psutil.process_iter")
def test_is_steam_running_handles_access_denied(
    mock_process_iter: MagicMock,
) -> None:
    """Test that is_steam_running handles psutil exceptions gracefully."""
    import psutil

    mock_process = MagicMock()
    mock_process.info.__getitem__ = MagicMock(
        side_effect=psutil.AccessDenied(pid=1)
    )
    mock_process_iter.return_value = [mock_process]
    assert is_steam_running() is False
