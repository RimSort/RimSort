from unittest.mock import MagicMock, patch

from app.utils.generic import (
    check_valid_http_git_url,
    extract_git_dir_name,
    extract_git_user_or_org,
    is_steam_running,
)

GIT_URLS = [
    "https://github.com/org/RimSort.git",
    "https://github.com/org/RimSort",
    "https://github.com/org/RimSort/",
    "http://github.com/org/RimSort.git",
    "github.com/org/RimSort.git",
    "github.com/org/RimSort",
    "github.com/org/RimSort/",
]


def test_get_git_dir_name() -> None:
    for url in GIT_URLS:
        assert extract_git_dir_name(url) == "RimSort"


def test_get_git_org_or_user() -> None:
    for url in GIT_URLS:
        assert extract_git_user_or_org(url) == "org"


def test_check_valid_http_git_url() -> None:
    assert check_valid_http_git_url("") is False

    assert check_valid_http_git_url("github.com/org/RimSort.git") is False

    assert check_valid_http_git_url("https://github.com/org/RimSort.git") is True

    assert check_valid_http_git_url("http://github.com/org/RimSort.git/") is True


def test_is_steam_running_steam_detected() -> None:
    """Test that is_steam_running returns True when Steam process is found"""
    mock_proc = MagicMock()
    mock_proc.info = {"name": "steam.exe"}

    with patch("app.utils.generic.platform.system", return_value="Windows"):
        with patch("psutil.process_iter", return_value=[mock_proc]):
            assert is_steam_running() is True


def test_is_steam_running_steam_not_detected() -> None:
    """Test that is_steam_running returns False when Steam process is not found"""
    mock_proc = MagicMock()
    mock_proc.info = {"name": "firefox.exe"}

    with patch("app.utils.generic.platform.system", return_value="Windows"):
        with patch("psutil.process_iter", return_value=[mock_proc]):
            assert is_steam_running() is False


def test_is_steam_running_linux_steamwebhelper() -> None:
    """Test that is_steam_running detects steamwebhelper on Linux"""
    mock_proc = MagicMock()
    mock_proc.info = {"name": "steamwebhelper"}

    with patch("app.utils.generic.platform.system", return_value="Linux"):
        with patch("psutil.process_iter", return_value=[mock_proc]):
            assert is_steam_running() is True


def test_is_steam_running_handles_process_exceptions() -> None:
    """Test that is_steam_running gracefully handles process access errors"""
    import psutil

    mock_proc = MagicMock()
    mock_proc.info = {"name": "steam.exe"}

    mock_proc_error = MagicMock()
    mock_proc_error.info.side_effect = psutil.NoSuchProcess(123)

    with patch("app.utils.generic.platform.system", return_value="Windows"):
        with patch("psutil.process_iter", return_value=[mock_proc_error, mock_proc]):
            assert is_steam_running() is True


def test_is_steam_running_unknown_platform() -> None:
    """Test that is_steam_running returns True on unknown platforms (fail open)"""
    with patch("app.utils.generic.platform.system", return_value="UnknownOS"):
        with patch("psutil.process_iter", return_value=[]):
            assert is_steam_running() is True


def test_is_steam_running_psutil_error() -> None:
    """Test that is_steam_running returns True on psutil errors (fail open)"""
    with patch("app.utils.generic.platform.system", return_value="Windows"):
        with patch("psutil.process_iter", side_effect=Exception("Mock error")):
            assert is_steam_running() is True
