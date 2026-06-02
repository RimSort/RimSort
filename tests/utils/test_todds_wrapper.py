"""Tests for app/utils/todds/wrapper.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.utils.todds.wrapper import ToddsInterface


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
        import platform

        todds_dir = tmp_path / "todds"
        todds_dir.mkdir()
        exe_name = "todds.exe" if platform.system() == "Windows" else "todds"
        todds_bin = todds_dir / exe_name
        todds_bin.touch()

        ti = ToddsInterface(preset="optimized")

        runner = MagicMock()
        runner.todds_dry_run_support = False

        with patch("app.utils.todds.wrapper.AppInfo") as mock_app_info:
            mock_app_info.return_value.application_folder = tmp_path
            ti.execute_todds_cmd("/some/target", runner)

        runner.execute.assert_called_once()
        args = runner.execute.call_args
        assert str(todds_bin) == args[0][0]

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
