"""Unit tests for update script launcher subprocess hardening."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.app_info import AppInfo
from app.utils.update_utils import ScriptConfig, UpdateManager


@pytest.fixture(autouse=True)
def _reset_appinfo_singleton() -> None:
    """Reset AppInfo singleton between tests."""
    AppInfo._instance = None


class TestScriptConfigArgs:
    """Test ScriptConfig argument list generation across platforms."""

    def test_build_bash_command_without_elevation(self) -> None:
        """Verify _build_bash_command returns list without sudo when unelevated."""
        base_args = ["/path/to/update.sh", "/tmp/update dir", "/var/log/update.log"]
        cmd = ScriptConfig._build_bash_command(base_args, needs_elevation=False)
        assert cmd == base_args

    def test_build_bash_command_with_elevation(self) -> None:
        """Verify _build_bash_command prepends sudo as list item when elevated."""
        base_args = ["/path/to/update.sh", "/tmp/update dir", "/var/log/update.log"]
        cmd = ScriptConfig._build_bash_command(base_args, needs_elevation=True)
        assert cmd == ["sudo", *base_args]

    @pytest.mark.parametrize(
        "terminal",
        ["konsole", "xterm", "x-terminal-emulator", "kitty"],
    )
    def test_build_terminal_command_standard_terminals(self, terminal: str) -> None:
        """Verify standard terminals use -e bash -c with list arguments."""
        base_args = ["/path/with space/update.sh", "/tmp/dir & special", "/log.txt"]
        cmd = ScriptConfig._build_terminal_command(
            terminal, base_args, needs_elevation=False
        )
        assert isinstance(cmd, list)
        assert cmd[0] == terminal
        assert cmd[1] == "-e"
        assert cmd[2] == "bash"
        assert cmd[3] == "-c"
        assert "read -p" in cmd[4]
        assert "'/path/with space/update.sh'" in cmd[4]
        assert "'/tmp/dir & special'" in cmd[4]

    def test_build_terminal_command_gnome(self) -> None:
        """Verify gnome-terminal uses -- bash -c with list arguments."""
        base_args = ["/path/update.sh", "/tmp/update", "/log.txt"]
        cmd = ScriptConfig._build_terminal_command(
            "gnome-terminal", base_args, needs_elevation=True
        )
        assert cmd == [
            "gnome-terminal",
            "--",
            "bash",
            "-c",
            "sudo /path/update.sh /tmp/update /log.txt",
        ]

    @pytest.mark.parametrize("terminal", ["xfce4-terminal", "mate-terminal"])
    def test_build_terminal_command_nested_quote_terminals(self, terminal: str) -> None:
        """Verify xfce4-terminal and mate-terminal use quoted -e arguments."""
        base_args = ["/path/update.sh", "/tmp/update", "/log.txt"]
        cmd = ScriptConfig._build_terminal_command(
            terminal, base_args, needs_elevation=False
        )
        assert isinstance(cmd, list)
        assert cmd[0] == terminal
        assert cmd[1] == "-e"
        assert cmd[2].startswith("bash -c ")

    def test_build_terminal_command_unknown_raises(self) -> None:
        """Verify unknown terminal emulator raises ValueError."""
        with pytest.raises(
            ValueError, match="Unknown terminal emulator: nonexistent-term"
        ):
            ScriptConfig._build_terminal_command(
                "nonexistent-term", ["a", "b"], needs_elevation=False
            )

    def test_darwin_args(self) -> None:
        """Verify Darwin platform generates osascript command as list."""
        cfg = ScriptConfig("update.sh", None, "Darwin")
        args = cfg.get_args(
            Path("/App/update.sh"),
            Path("/tmp/update dir"),
            Path("/tmp/log.txt"),
            needs_elevation=False,
        )
        assert isinstance(args, list)
        assert args[0] == "osascript"
        assert args[1] == "-e"
        assert 'tell app "Terminal" to do script' in args[2]

    def test_windows_args_non_elevated(self, tmp_path: Path) -> None:
        """Verify Windows non-elevated generates list starting with cmd /k."""
        cfg = ScriptConfig("update.bat", None, "Windows")
        script = tmp_path / "update.bat"
        temp = tmp_path / "temp update"
        log = tmp_path / "update.log"
        args = cfg.get_args(script, temp, log, needs_elevation=False)
        assert args == ["cmd", "/k", str(script), str(temp), str(log)]

    def test_windows_args_elevated(self, tmp_path: Path) -> None:
        """Verify Windows elevated generates list starting with powershell.exe."""
        cfg = ScriptConfig("update.bat", None, "Windows")
        script = tmp_path / "update.bat"
        temp = tmp_path / "temp & update"
        log = tmp_path / "update.log"
        args = cfg.get_args(script, temp, log, needs_elevation=True)
        assert isinstance(args, list)
        assert args[0] == "powershell.exe"
        assert "-NoProfile" in args
        assert "-ExecutionPolicy" in args
        assert "Bypass" in args
        assert "-Command" in args
        assert "Start-Process cmd" in args[-1]
        assert "RunAs" in args[-1]
        assert args[-1].endswith("-Verb RunAs -WindowStyle Normal")


class TestLaunchWindowsUpdateScript:
    """Test Windows update script execution without shell=True."""

    @patch("app.utils.update_utils.subprocess.Popen")
    def test_launch_windows_non_elevated(
        self, mock_popen: MagicMock, tmp_path: Path
    ) -> None:
        """Verify non-elevated launch uses CREATE_NEW_CONSOLE and no shell=True."""
        mgr = MagicMock(spec=UpdateManager)
        mgr._system = "Windows"

        script = tmp_path / "dir with space & special" / "update.bat"
        temp = tmp_path / "temp folder"
        log = tmp_path / "log & test.txt"
        args_repr = ["cmd", "/k", str(script), str(temp), str(log)]

        UpdateManager._launch_windows_update_script(
            mgr, script, args_repr, needs_elevation=False
        )

        mock_popen.assert_called_once()
        call_args, call_kwargs = mock_popen.call_args

        # shell=True must NOT be present
        assert call_kwargs.get("shell") is not True

        # CREATE_NEW_CONSOLE flag must be present
        expected_flag = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
        assert call_kwargs.get("creationflags") == expected_flag

        assert call_args[0] == args_repr

    @patch("app.utils.update_utils.subprocess.Popen")
    def test_launch_windows_elevated(
        self, mock_popen: MagicMock, tmp_path: Path
    ) -> None:
        """Verify elevated launch runs powershell list args without shell=True."""
        mgr = MagicMock(spec=UpdateManager)
        mgr._system = "Windows"

        script = tmp_path / "update.bat"
        args_repr = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Start-Process cmd -Verb RunAs",
        ]

        UpdateManager._launch_windows_update_script(
            mgr, script, args_repr, needs_elevation=True
        )

        mock_popen.assert_called_once()
        call_args, call_kwargs = mock_popen.call_args

        # shell=True must NOT be present
        assert call_kwargs.get("shell") is not True
        assert call_args[0] == args_repr


class TestLaunchPosixUpdateScript:
    """Test POSIX update script execution without shell=True."""

    @patch("app.utils.update_utils.subprocess.Popen")
    def test_launch_posix_primary_method(
        self, mock_popen: MagicMock, tmp_path: Path
    ) -> None:
        """Verify primary POSIX launch executes argument list without shell=True."""
        mgr = MagicMock(spec=UpdateManager)
        mgr._system = "Linux"

        script = tmp_path / "update.sh"
        script.touch()
        temp = tmp_path / "temp update"
        log = tmp_path / "log.txt"
        install_dir = tmp_path / "install"
        args_repr = [str(script), str(temp), str(log), str(install_dir)]

        UpdateManager._launch_posix_update_script(
            mgr,
            script,
            args_repr,
            needs_elevation=False,
            update_source_path=temp,
            log_path=log,
            install_dir=install_dir,
        )

        mock_popen.assert_called_once()
        call_args, call_kwargs = mock_popen.call_args
        assert call_kwargs.get("shell") is not True
        assert call_args[0] == args_repr

    @patch("app.utils.update_utils.subprocess.Popen")
    def test_launch_posix_terminal_fallback(
        self, mock_popen: MagicMock, tmp_path: Path
    ) -> None:
        """Verify Linux terminal fallback executes without shell=True."""
        mgr = MagicMock(spec=UpdateManager)
        mgr._system = "Linux"
        mgr._detect_terminal_emulator.return_value = "gnome-terminal"
        mgr._script_configs = {"Linux": ScriptConfig("update.sh", None, "Linux")}

        script = tmp_path / "update.sh"
        script.touch()
        temp = tmp_path / "temp update"
        log = tmp_path / "log.txt"
        install_dir = tmp_path / "install"
        args_repr = [str(script), str(temp), str(log), str(install_dir)]

        # First call (primary direct execution) fails, triggering fallback
        fallback_popen = MagicMock()
        mock_popen.side_effect = [OSError("Direct execution failed"), fallback_popen]

        res = UpdateManager._launch_posix_update_script(
            mgr,
            script,
            args_repr,
            needs_elevation=False,
            update_source_path=temp,
            log_path=log,
            install_dir=install_dir,
        )

        assert res == fallback_popen
        assert mock_popen.call_count == 2
        fallback_call_args, fallback_call_kwargs = mock_popen.call_args_list[1]
        assert fallback_call_kwargs.get("shell") is not True
        assert fallback_call_args[0][0] == "gnome-terminal"
        assert fallback_call_args[0][1] == "--"
