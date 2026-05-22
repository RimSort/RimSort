"""
Unit tests for the launch_command_parser module.

Tests the parsing of Steam-style %command% syntax including environment
variables, wrapper executables, and game arguments.
"""

from app.utils.launch_command_parser import ParsedLaunchCommand, parse_launch_command


class TestParseBasicEnvVar:
    """Tests for basic environment variable parsing."""

    def test_single_env_var(self) -> None:
        result = parse_launch_command("PROTON_LOG=1 %command%")
        assert result.env_vars == {"PROTON_LOG": "1"}
        assert result.wrapper_commands == []
        assert result.game_args == []

    def test_multiple_env_vars(self) -> None:
        result = parse_launch_command("FOO=1 BAR=2 %command%")
        assert result.env_vars == {"FOO": "1", "BAR": "2"}
        assert result.wrapper_commands == []
        assert result.game_args == []

    def test_env_var_with_empty_value(self) -> None:
        result = parse_launch_command("FOO= %command%")
        assert result.env_vars == {"FOO": ""}
        assert result.wrapper_commands == []
        assert result.game_args == []

    def test_env_var_with_complex_value(self) -> None:
        result = parse_launch_command("PATH=/usr/bin:/bin %command%")
        assert result.env_vars == {"PATH": "/usr/bin:/bin"}

    def test_quoted_env_var_value(self) -> None:
        result = parse_launch_command('VAR="value with spaces" %command%')
        assert result.env_vars == {"VAR": "value with spaces"}
        assert result.wrapper_commands == []
        assert result.game_args == []

    def test_env_var_with_equals_in_value(self) -> None:
        result = parse_launch_command('VAR="key=value" %command%')
        assert result.env_vars == {"VAR": "key=value"}


class TestParseWrapperCommands:
    """Tests for wrapper executable parsing."""

    def test_single_wrapper(self) -> None:
        result = parse_launch_command("gamemoderun %command%")
        assert result.env_vars == {}
        assert result.wrapper_commands == ["gamemoderun"]
        assert result.game_args == []

    def test_multiple_wrappers(self) -> None:
        result = parse_launch_command("wrapper1 wrapper2 %command%")
        assert result.env_vars == {}
        assert result.wrapper_commands == ["wrapper1", "wrapper2"]
        assert result.game_args == []

    def test_wrapper_with_path(self) -> None:
        result = parse_launch_command("/usr/bin/gamemoderun %command%")
        assert result.wrapper_commands == ["/usr/bin/gamemoderun"]


class TestParseCombinedUsage:
    """Tests for combined env vars, wrappers, and args."""

    def test_env_and_wrapper(self) -> None:
        result = parse_launch_command("DXVK_HUD=1 gamemoderun %command%")
        assert result.env_vars == {"DXVK_HUD": "1"}
        assert result.wrapper_commands == ["gamemoderun"]
        assert result.game_args == []

    def test_env_wrapper_and_args(self) -> None:
        result = parse_launch_command(
            "DXVK_HUD=1 gamemoderun %command% -logfile /tmp/log"
        )
        assert result.env_vars == {"DXVK_HUD": "1"}
        assert result.wrapper_commands == ["gamemoderun"]
        assert result.game_args == ["-logfile", "/tmp/log"]

    def test_multiple_env_and_multiple_wrappers(self) -> None:
        result = parse_launch_command("FOO=1 BAR=2 wrap1 wrap2 %command% -arg1 -arg2")
        assert result.env_vars == {"FOO": "1", "BAR": "2"}
        assert result.wrapper_commands == ["wrap1", "wrap2"]
        assert result.game_args == ["-arg1", "-arg2"]


class TestParseGameArgs:
    """Tests for game argument parsing."""

    def test_only_game_args(self) -> None:
        result = parse_launch_command("%command% -arg1 -arg2")
        assert result.env_vars == {}
        assert result.wrapper_commands == []
        assert result.game_args == ["-arg1", "-arg2"]

    def test_args_with_values(self) -> None:
        result = parse_launch_command("%command% -logfile /tmp/log -popupwindow")
        assert result.game_args == ["-logfile", "/tmp/log", "-popupwindow"]

    def test_args_with_spaces_in_paths(self) -> None:
        result = parse_launch_command('%command% -logfile "/path/with spaces/log.txt"')
        assert result.game_args == ["-logfile", "/path/with spaces/log.txt"]

    def test_args_with_equals_sign(self) -> None:
        result = parse_launch_command("%command% -savedatafolder=/path/to/save")
        assert result.game_args == ["-savedatafolder=/path/to/save"]


class TestParseEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_no_command_placeholder(self) -> None:
        """When no %command% is present, treat all tokens as game args."""
        result = parse_launch_command("-logfile /tmp/log")
        assert result.env_vars == {}
        assert result.wrapper_commands == []
        assert result.game_args == ["-logfile", "/tmp/log"]

    def test_multiple_command_placeholders(self) -> None:
        """First %command% is the placeholder, rest are literal args."""
        result = parse_launch_command("%command% %command%")
        assert result.env_vars == {}
        assert result.wrapper_commands == []
        assert result.game_args == ["%command%"]

    def test_empty_string(self) -> None:
        result = parse_launch_command("")
        assert result.env_vars == {}
        assert result.wrapper_commands == []
        assert result.game_args == []

    def test_whitespace_only(self) -> None:
        result = parse_launch_command("   ")
        assert result.env_vars == {}
        assert result.wrapper_commands == []
        assert result.game_args == []

    def test_command_placeholder_only(self) -> None:
        result = parse_launch_command("%command%")
        assert result.env_vars == {}
        assert result.wrapper_commands == []
        assert result.game_args == []

    def test_unclosed_quotes(self) -> None:
        """Unclosed quotes should be handled gracefully."""
        result = parse_launch_command('VAR="unclosed %command%')
        # shlex will fail, fall back to treating as game args
        assert result.game_args == ['VAR="unclosed %command%']

    def test_complex_real_world_example(self) -> None:
        """Test a complex real-world Steam launch options example."""
        result = parse_launch_command(
            'PROTON_LOG=1 DXVK_HUD=fps mangohud gamemoderun %command% -logfile "/home/user/logs/rimworld.log" -popupwindow'
        )
        assert result.env_vars == {"PROTON_LOG": "1", "DXVK_HUD": "fps"}
        assert result.wrapper_commands == ["mangohud", "gamemoderun"]
        assert result.game_args == [
            "-logfile",
            "/home/user/logs/rimworld.log",
            "-popupwindow",
        ]


class TestParseDataclass:
    """Tests for the ParsedLaunchCommand dataclass."""

    def test_default_construction(self) -> None:
        """Test that dataclass defaults to empty collections."""
        parsed = ParsedLaunchCommand()
        assert parsed.env_vars == {}
        assert parsed.wrapper_commands == []
        assert parsed.game_args == []

    def test_explicit_construction(self) -> None:
        """Test explicit construction of ParsedLaunchCommand."""
        parsed = ParsedLaunchCommand(
            env_vars={"FOO": "bar"}, wrapper_commands=["wrapper"], game_args=["-arg"]
        )
        assert parsed.env_vars == {"FOO": "bar"}
        assert parsed.wrapper_commands == ["wrapper"]
        assert parsed.game_args == ["-arg"]
