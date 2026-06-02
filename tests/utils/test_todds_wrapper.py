"""Tests for app/utils/todds/wrapper.py."""

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
