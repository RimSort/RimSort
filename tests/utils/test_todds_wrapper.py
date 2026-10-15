"""Tests for app/utils/todds/wrapper.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.todds.wrapper import ToddsInterface


def _touch_bundled_todds(application_folder: Path) -> Path:
    """Create the platform-specific bundled todds executable."""
    import platform

    executable_name = "todds.exe" if platform.system() == "Windows" else "todds"
    todds_binary = application_folder / "todds" / executable_name
    todds_binary.parent.mkdir(parents=True, exist_ok=True)
    todds_binary.touch()
    return todds_binary


def _execute_with_application_folder(
    application_folder: Path,
) -> tuple[MagicMock, MagicMock]:
    """Execute todds against a mocked application folder."""
    todds_interface = ToddsInterface(preset="optimized")
    runner = MagicMock()
    runner.todds_dry_run_support = False

    with patch("app.utils.todds.wrapper.AppInfo") as mock_app_info:
        mock_app_info.return_value.application_folder = application_folder
        todds_interface.execute_todds_cmd("/some/target", runner)

    runner.execute.assert_called_once()
    return runner, mock_app_info


class TestToddsInterfaceInit:
    """Test ToddsInterface initialization with various parameter combinations."""

    def test_optimized_preset_default(self) -> None:
        """Test that optimized preset is initialized correctly."""
        ti = ToddsInterface(preset="optimized")
        assert ti.preset == "optimized"
        assert "-f" in ti.todds_presets["optimized"]
        assert "BC1" in ti.todds_presets["optimized"]

    def test_clean_preset(self) -> None:
        """Test that clean preset is initialized correctly."""
        ti = ToddsInterface(preset="clean")
        assert ti.preset == "clean"
        assert "-cl" in ti.todds_presets["clean"]

    def test_custom_preset_uses_passed_command(self) -> None:
        """Test that custom preset uses the passed custom_command parameter."""
        ti = ToddsInterface(preset="custom", custom_command="-f BC3 -o")
        assert ti.preset == "custom"
        assert ti.custom_args == ["-f", "BC3", "-o"]

    def test_custom_preset_without_command_has_empty_args(self) -> None:
        """Test that custom preset with empty command has empty args."""
        ti = ToddsInterface(preset="custom", custom_command="")
        assert ti.preset == "custom"
        assert ti.custom_args == []

    def test_overwrite_flag_enabled(self) -> None:
        """Test that overwrite flag is set correctly when enabled."""
        ti = ToddsInterface(preset="optimized", overwrite=True)
        assert "-o" in ti.todds_presets["optimized"]
        assert "-on" not in ti.todds_presets["optimized"]

    def test_overwrite_flag_disabled(self) -> None:
        """Test that overwrite flag is set correctly when disabled."""
        ti = ToddsInterface(preset="optimized", overwrite=False)
        assert "-on" in ti.todds_presets["optimized"]
        assert "-o" not in ti.todds_presets["optimized"]

    def test_dry_run_removes_parallel_flags(self) -> None:
        """Test that dry run removes parallel flags and adds dry run flags."""
        ti = ToddsInterface(preset="optimized", dry_run=True)
        args = ti.todds_presets["optimized"]
        assert "-p" not in args
        assert "-v" in args
        assert "-dr" in args


class TestToddsExecute:
    def test_execute_calls_runner_when_binary_exists(self, tmp_path: Path) -> None:
        """When todds binary exists, execute_todds_cmd calls runner.execute."""
        todds_binary = _touch_bundled_todds(tmp_path)

        runner, _ = _execute_with_application_folder(tmp_path)

        args = runner.execute.call_args
        assert str(todds_binary) == args[0][0]

    def test_execute_shows_error_when_binary_missing(self, tmp_path: Path) -> None:
        """When todds binary is missing, execute_todds_cmd sends error message."""
        ti = ToddsInterface(preset="optimized")
        runner = MagicMock()
        runner.todds_dry_run_support = False

        with patch("app.utils.todds.wrapper.AppInfo") as mock_app_info:
            mock_app_info.return_value.application_folder = tmp_path
            ti.execute_todds_cmd("/some/target", runner)

        runner.execute.assert_not_called()
        runner.message.assert_called_once()
        assert "ERROR" in runner.message.call_args[0][0]


class TestToddsEnvOverride:
    """RIMSORT_TODDS_PATH lets packagers (e.g. Nix) point at a system todds
    instead of the one bundled next to the application folder."""

    def test_env_override_used_instead_of_bundled_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        system_todds = tmp_path / "nix" / "bin" / "todds"
        system_todds.parent.mkdir(parents=True)
        system_todds.touch()
        monkeypatch.setenv("RIMSORT_TODDS_PATH", str(system_todds))

        runner, mock_app_info = _execute_with_application_folder(tmp_path)

        assert runner.execute.call_args[0][0] == str(system_todds)
        mock_app_info.assert_not_called()

    def test_env_override_missing_binary_reports_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "RIMSORT_TODDS_PATH", str(tmp_path / "nix" / "bin" / "todds")
        )

        ti = ToddsInterface(preset="optimized")
        runner = MagicMock()
        runner.todds_dry_run_support = False

        ti.execute_todds_cmd("/some/target", runner)

        runner.execute.assert_not_called()
        runner.message.assert_called_once()
        assert "ERROR" in runner.message.call_args[0][0]

    def test_empty_env_falls_back_to_bundled_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RIMSORT_TODDS_PATH", "")
        todds_binary = _touch_bundled_todds(tmp_path)

        runner, _ = _execute_with_application_folder(tmp_path)

        assert runner.execute.call_args[0][0] == str(todds_binary)
