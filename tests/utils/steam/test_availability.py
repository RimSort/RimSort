import sys
from unittest.mock import MagicMock, patch

from app.utils.steam.availability import (
    _STEAM_LAUNCH_BEHAVIOR_ALWAYS,  # noqa: F401
    _STEAM_LAUNCH_BEHAVIOR_NEVER,  # noqa: F401
    _STEAM_LAUNCH_BEHAVIOR_PROMPT,  # noqa: F401
    is_steam_running,
)


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
    mock_process.info.__getitem__ = MagicMock(side_effect=psutil.AccessDenied(pid=1))
    mock_process_iter.return_value = [mock_process]
    assert is_steam_running() is False


def _make_settings(
    behavior: str = "prompt", steam_client_integration: bool = True
) -> MagicMock:
    """Create a mock Settings object with the given steam launch behavior."""
    settings = MagicMock()
    settings.steam_launch_behavior = behavior
    settings.current_instance = "default"
    instance = MagicMock()
    instance.steam_client_integration = steam_client_integration
    settings.instances = {"default": instance}
    return settings


@patch("app.utils.steam.availability.is_steam_running", return_value=True)
def test_check_steam_available_returns_true_when_steam_running(
    mock_running: MagicMock,
) -> None:
    from app.utils.steam.availability import check_steam_available

    settings = _make_settings()
    assert check_steam_available(_libs="/fake", settings=settings) is True


@patch("app.utils.steam.availability.is_steam_running", return_value=True)
def test_check_steam_available_skips_check_when_integration_disabled(
    mock_running: MagicMock,
) -> None:
    from app.utils.steam.availability import check_steam_available

    settings = _make_settings(steam_client_integration=False)
    assert check_steam_available(_libs="/fake", settings=settings) is True
    mock_running.assert_not_called()


@patch("app.utils.steam.availability.is_steam_running", return_value=False)
@patch("app.utils.steam.availability.show_no_steam_warning")
def test_check_steam_available_never_shows_warning(
    mock_warning: MagicMock,
    mock_running: MagicMock,
) -> None:
    from app.utils.steam.availability import check_steam_available

    settings = _make_settings(behavior="never")
    assert check_steam_available(_libs="/fake", settings=settings) is False
    mock_warning.assert_called_once()
