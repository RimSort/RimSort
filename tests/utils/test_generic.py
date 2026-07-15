from unittest.mock import MagicMock, patch

from app.utils.generic import (
    check_valid_http_git_url,
    extract_git_dir_name,
    extract_git_user_or_org,
    restart_application,
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


class TestRestartApplication:
    def test_non_frozen_reconstructs_module_invocation(self) -> None:
        """Regression test: `python -m app` sets sys.argv[0] to the resolved
        path of app/__main__.py, not "-m app". Re-launching with
        [sys.executable] + sys.argv (the old behavior) ran that path as a
        plain script, which put app/ instead of the project root on
        sys.path and broke `from app...` imports on restart."""
        with (
            patch("app.utils.generic.sys") as mock_sys,
            patch("app.utils.generic.subprocess.Popen") as mock_popen,
            patch("app.utils.generic.QApplication") as mock_qapp,
        ):
            mock_sys.frozen = False
            mock_sys.executable = "C:\\Python\\python.exe"
            mock_sys.argv = ["C:\\RimSort\\app\\__main__.py", "--extra"]
            mock_qapp.instance.return_value = MagicMock()

            restart_application()

            mock_popen.assert_called_once_with(
                ["C:\\Python\\python.exe", "-m", "app", "--extra"]
            )

    def test_frozen_reuses_executable_directly(self) -> None:
        with (
            patch("app.utils.generic.sys") as mock_sys,
            patch("app.utils.generic.subprocess.Popen") as mock_popen,
            patch("app.utils.generic.QApplication") as mock_qapp,
        ):
            mock_sys.frozen = True
            mock_sys.executable = "C:\\RimSort\\RimSort.exe"
            mock_sys.argv = ["C:\\RimSort\\RimSort.exe", "--extra"]
            mock_qapp.instance.return_value = MagicMock()

            restart_application()

            mock_popen.assert_called_once_with(["C:\\RimSort\\RimSort.exe", "--extra"])
