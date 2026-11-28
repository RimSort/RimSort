"""Unit tests for update script launcher subprocess hardening."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.app_info import AppInfo
from app.utils.update_utils import ScriptConfig, UpdateManager


def _create_recording_script(script_path: Path) -> Path:
    """Create an executable shell script that records its arguments."""
    script_path.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "${0}.received"\n',
        encoding="utf-8",
    )
    return Path(f"{script_path}.received")


def _launch_posix_script_and_assert_args(
    manager: MagicMock,
    script_path: Path,
    args_repr: list[str],
    update_source_path: Path,
    log_path: Path,
    install_dir: Path,
    result_file: Path,
) -> None:
    """Launch a POSIX update script and assert that it receives each path intact."""
    process = UpdateManager._launch_posix_update_script(
        manager,
        script_path,
        args_repr,
        needs_elevation=False,
        update_source_path=update_source_path,
        log_path=log_path,
        install_dir=install_dir,
    )
    assert process.wait(timeout=10) == 0
    assert result_file.read_text(encoding="utf-8").splitlines() == [
        str(update_source_path),
        str(log_path),
        str(install_dir),
    ]


class TestScriptConfigArgs:
    """Test ScriptConfig argument list generation across platforms."""

    def test_build_direct_command_without_elevation(self) -> None:
        """Verify _build_direct_command returns args without sudo when unelevated."""
        base_args = ["/path/to/update.sh", "/tmp/update dir", "/var/log/update.log"]
        cmd = ScriptConfig._build_direct_command(base_args, needs_elevation=False)
        assert cmd == base_args

    def test_build_direct_command_with_elevation(self) -> None:
        """Verify _build_direct_command prepends sudo when elevated."""
        base_args = ["/path/to/update.sh", "/tmp/update dir", "/var/log/update.log"]
        cmd = ScriptConfig._build_direct_command(base_args, needs_elevation=True)
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
            Path('/tmp/update "quoted" \\ folder'),
            Path("/tmp/log.txt"),
            needs_elevation=False,
        )
        assert isinstance(args, list)
        assert args[0] == "osascript"
        assert args[1] == "-e"
        assert 'tell app "Terminal" to do script' in args[2]
        assert r"read -p \"Press enter to close\"" in args[2]
        assert r"\"quoted\"" in args[2]
        assert r"\\ folder" in args[2]

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
        install_dir = tmp_path / "RimSort install &; target"
        AppInfo()._application_folder = install_dir

        args = cfg.get_args(script, temp, log, needs_elevation=True)
        assert isinstance(args, list)
        assert args[0] == "powershell.exe"
        assert "-NoProfile" in args
        assert "-ExecutionPolicy" in args
        assert "Bypass" in args
        assert "-Command" in args
        assert "Start-Process cmd" in args[-1]
        assert "RunAs" in args[-1]
        assert f'cd /d "{install_dir}"' in args[-1]
        assert f'cd /d "{script.parent}"' not in args[-1]
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

        script = tmp_path / "dir with space &; special" / "update.bat"
        temp = tmp_path / "temp folder &; special"
        log = tmp_path / "log &; test.txt"
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

        assert call_args[0] == f'cmd /d /k ""{script}" "{temp}" "{log}""'

    @pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows cmd")
    def test_launch_windows_non_elevated_runs_batch_with_special_character_paths(
        self, tmp_path: Path
    ) -> None:
        """Verify cmd preserves paths containing spaces, ampersands, and semicolons."""
        script_dir = tmp_path / "script dir &; special"
        script_dir.mkdir()
        script = script_dir / "record_args.bat"
        result_file = script_dir / "received.txt"
        temp = tmp_path / "update source &; special"
        log = tmp_path / "update log &; special.txt"
        script.write_text(
            "@echo off\n"
            f'>"{result_file}" echo("%~1"\n'
            f'>>"{result_file}" echo("%~2"\n'
            "exit\n",
            encoding="utf-8",
            newline="\r\n",
        )
        args_repr = ["cmd", "/k", str(script), str(temp), str(log)]

        process = UpdateManager._launch_windows_update_script(
            MagicMock(spec=UpdateManager),
            script,
            args_repr,
            needs_elevation=False,
        )
        try:
            return_code = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            pytest.fail("cmd did not finish running the temporary batch script")

        assert return_code == 0
        assert result_file.read_text(encoding="utf-8").splitlines() == [
            f'"{temp}"',
            f'"{log}"',
        ]

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

    @pytest.mark.skipif(
        sys.platform != "linux", reason="Requires Linux direct execution"
    )
    def test_launch_posix_primary_executes_script_with_special_character_paths(
        self, tmp_path: Path
    ) -> None:
        """Verify direct exec preserves paths with spaces, ampersands, and semicolons."""
        script_dir = tmp_path / "script dir &; special"
        script_dir.mkdir()
        script = script_dir / "record_args.sh"
        result_file = _create_recording_script(script)
        temp = tmp_path / "update source &; special"
        log = tmp_path / "update log &; special.txt"
        install_dir = tmp_path / "install dir &; special"
        args_repr = [str(script), str(temp), str(log), str(install_dir)]

        _launch_posix_script_and_assert_args(
            MagicMock(spec=UpdateManager),
            script,
            args_repr,
            temp,
            log,
            install_dir,
            result_file,
        )

    @pytest.mark.skipif(
        sys.platform != "linux", reason="Requires Linux terminal fallback"
    )
    def test_launch_posix_terminal_fallback_executes_script_with_special_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify the fallback terminal passes special-character paths to bash."""
        script_dir = tmp_path / "script dir &; special"
        script_dir.mkdir()
        script = script_dir / "record_args.sh"
        result_file = _create_recording_script(script)

        terminal_dir = tmp_path / "bin"
        terminal_dir.mkdir()
        terminal = terminal_dir / "gnome-terminal"
        terminal.write_text(
            '#!/bin/sh\nif [ "$1" = "--" ]; then shift; fi\nexec "$@"\n',
            encoding="utf-8",
        )
        terminal.chmod(0o755)
        monkeypatch.setenv("PATH", f"{terminal_dir}{os.pathsep}{os.environ['PATH']}")

        temp = tmp_path / "update source &; special"
        log = tmp_path / "update log &; special.txt"
        install_dir = tmp_path / "install dir &; special"
        args_repr = [str(tmp_path / "missing-update.sh"), str(temp), str(log)]
        manager = MagicMock(spec=UpdateManager)
        manager._system = "Linux"
        manager._detect_terminal_emulator.return_value = "gnome-terminal"
        manager._script_configs = {"Linux": ScriptConfig("update.sh", None, "Linux")}

        _launch_posix_script_and_assert_args(
            manager,
            script,
            args_repr,
            temp,
            log,
            install_dir,
            result_file,
        )

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
