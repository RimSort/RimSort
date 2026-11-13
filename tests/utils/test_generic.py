from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import app.utils.generic
from app.utils.generic import (
    apply_launch_prefix,
    check_valid_http_git_url,
    extract_git_dir_name,
    extract_git_user_or_org,
    platform_specific_open,
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


class TestPlatformSpecificOpen:
    @pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
    @pytest.mark.parametrize("as_string", [False, True])
    def test_missing_path_warns_without_opening(
        self, tmp_path: Path, platform: str, as_string: bool
    ) -> None:
        missing = tmp_path / "missing" / "mods"
        path = str(missing) if as_string else missing
        with (
            patch("app.utils.generic.sys") as mock_sys,
            patch("app.utils.generic.os.startfile", create=True) as startfile,
            patch("app.utils.generic.subprocess.Popen") as popen,
            patch("app.utils.generic.dialogue.show_warning") as warning,
        ):
            mock_sys.platform = platform

            platform_specific_open(path)

            warning.assert_called_once_with(
                title="Path not found",
                text="The selected path does not exist.",
                details=str(missing),
            )
            startfile.assert_not_called()
            popen.assert_not_called()

    @pytest.mark.parametrize("winerror", [2, 3])
    def test_windows_path_disappearing_during_open_warns(
        self, tmp_path: Path, winerror: int
    ) -> None:
        error = FileNotFoundError("Path disappeared")
        with (
            patch.object(error, "winerror", winerror, create=True),
            patch("app.utils.generic.sys") as mock_sys,
            patch(
                "app.utils.generic.os.startfile", create=True, side_effect=error
            ) as startfile,
            patch("app.utils.generic.subprocess.Popen") as popen,
            patch("app.utils.generic.dialogue.show_warning") as warning,
        ):
            mock_sys.platform = "win32"

            platform_specific_open(tmp_path)

            startfile.assert_called_once_with(str(tmp_path))
            warning.assert_called_once_with(
                title="Path not found",
                text="The selected path does not exist.",
                details=str(tmp_path),
            )
            popen.assert_not_called()

    @pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
    @pytest.mark.parametrize("target", ["directory", "file", "steam_uri", "app"])
    def test_existing_paths_and_uris_keep_platform_dispatch(
        self, tmp_path: Path, platform: str, target: str
    ) -> None:
        match target:
            case "directory":
                path = str(tmp_path)
            case "file":
                file = tmp_path / "About.xml"
                file.touch()
                path = str(file)
            case "app":
                app = tmp_path / "RimWorld.app"
                app.mkdir()
                path = str(app)
            case _:
                path = "steam://validate/294100"
        with (
            patch("app.utils.generic.sys") as mock_sys,
            patch("app.utils.generic.os.startfile", create=True) as startfile,
            patch("app.utils.generic.subprocess.Popen") as popen,
            patch("app.utils.generic.dialogue.show_warning") as warning,
        ):
            mock_sys.platform = platform

            platform_specific_open(path)

            warning.assert_not_called()
            if platform == "win32":
                startfile.assert_called_once_with(path)
                popen.assert_not_called()
            else:
                startfile.assert_not_called()
                if platform == "darwin":
                    command = ["open", path]
                    if target == "app":
                        command.append("-R")
                    popen.assert_called_once_with(command)
                else:
                    popen.assert_called_once()
                    assert popen.call_args.args == (["xdg-open", path],)
                    assert popen.call_args.kwargs["env"]["LD_LIBRARY_PATH"] == ""

    @pytest.mark.parametrize("winerror", [-2147221003, 5])
    def test_windows_other_errors_keep_existing_behavior(
        self, tmp_path: Path, winerror: int
    ) -> None:
        error = OSError("Cannot open")
        with (
            patch.object(error, "winerror", winerror, create=True),
            patch("app.utils.generic.sys") as mock_sys,
            patch("app.utils.generic.os.startfile", create=True, side_effect=error),
            patch("app.utils.generic.subprocess.Popen") as popen,
            patch("app.utils.generic.dialogue.show_warning") as warning,
        ):
            mock_sys.platform = "win32"

            if winerror == -2147221003:
                platform_specific_open(tmp_path)
                popen.assert_called_once_with(["notepad.exe", str(tmp_path)])
            else:
                with pytest.raises(OSError) as caught:
                    platform_specific_open(tmp_path)
                assert caught.value is error
                popen.assert_not_called()
            warning.assert_not_called()


class TestRestartApplication:
    def _assert_helper_invocation(
        self, mock_popen: MagicMock, executable: str, cmd: list[str]
    ) -> None:
        """Restarting spawns a detached helper through this
        executable's own entry point that waits for the single-instance
        lock to clear before relaunching, so the Popen call wraps the
        real command instead of being it."""
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        delayed = args[0]
        assert kwargs["creationflags"] == 0
        assert delayed[0] == executable
        flag_index = delayed.index("--restart-helper")
        assert "rimsort.lock" in delayed[flag_index + 1]
        assert delayed[flag_index + 2 :] == cmd

    def test_non_frozen_reconstructs_module_invocation(self) -> None:
        """Regression test: `python -m app` sets sys.argv[0] to the resolved
        path of app/__main__.py, not "-m app". Re-launching with that path
        directly runs it as a plain script, which puts app/ instead of the
        project root on sys.path and breaks `from app...` imports on
        restart, so the -m invocation is reconstructed."""
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

            self._assert_helper_invocation(
                mock_popen,
                "C:\\Python\\python.exe",
                ["C:\\Python\\python.exe", "-m", "app", "--extra"],
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

            self._assert_helper_invocation(
                mock_popen,
                "C:\\RimSort\\RimSort.exe",
                ["C:\\RimSort\\RimSort.exe", "--extra"],
            )

    def test_nuitka_build_without_sys_frozen_reuses_executable(self) -> None:
        """macOS Nuitka bundles leave sys.frozen unset. Adding -m app
        there makes the bundle reject its own invocation with exit
        code 2, so the helper must detect __compiled__ instead."""
        executable = "/Applications/RimSort.app/Contents/MacOS/RimSort"
        with (
            patch("app.utils.generic.sys") as mock_sys,
            patch("app.utils.generic.subprocess.Popen") as mock_popen,
            patch("app.utils.generic.QApplication") as mock_qapp,
            patch.dict(app.utils.generic.__dict__, {"__compiled__": object()}),
        ):
            mock_sys.frozen = False
            mock_sys.executable = executable
            mock_sys.argv = [executable]
            mock_qapp.instance.return_value = MagicMock()

            restart_application()

            self._assert_helper_invocation(mock_popen, executable, [executable])


class TestApplyLaunchPrefix:
    """Cover RIMSORT_LAUNCH_PREFIX handling for packaged builds that must
    launch executables inside an FHS environment (e.g. Nix steam-run)."""

    def test_unset_returns_launch_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("RIMSORT_LAUNCH_PREFIX", raising=False)

        assert apply_launch_prefix("/games/RimWorld", ["-a"]) == (
            "/games/RimWorld",
            ["-a"],
        )

    def test_blank_value_is_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RIMSORT_LAUNCH_PREFIX", "   ")

        assert apply_launch_prefix("/games/RimWorld", ["-a"]) == (
            "/games/RimWorld",
            ["-a"],
        )

    def test_prefix_prepended_on_linux(self, nix_launch_prefix: str) -> None:
        program, args = apply_launch_prefix("/games/RimWorld", ["-logfile", "x"])

        assert program == nix_launch_prefix
        assert args == ["/games/RimWorld", "-logfile", "x"]

    def test_multiword_prefix_is_shell_split(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RIMSORT_LAUNCH_PREFIX", "run --env='A B' --")
        monkeypatch.setattr("app.utils.generic.platform.system", lambda: "Linux")

        program, args = apply_launch_prefix("/games/RimWorld", [])

        assert program == "run"
        assert args == ["--env=A B", "--", "/games/RimWorld"]

    def test_ignored_on_non_linux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "RIMSORT_LAUNCH_PREFIX", "/nix/store/x-steam-run/bin/steam-run"
        )
        monkeypatch.setattr("app.utils.generic.platform.system", lambda: "Windows")

        assert apply_launch_prefix("/games/RimWorld", ["-a"]) == (
            "/games/RimWorld",
            ["-a"],
        )
