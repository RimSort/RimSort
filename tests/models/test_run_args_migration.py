"""Tests for run_args list-to-str migration during settings deserialization."""

from app.models.settings import Settings


class TestMigrateRunArgsValue:
    """Tests for Settings._migrate_run_args_value."""

    def test_empty_list(self) -> None:
        assert Settings._migrate_run_args_value([]) == ""

    def test_string_passthrough(self) -> None:
        assert (
            Settings._migrate_run_args_value("-logfile /tmp/log") == "-logfile /tmp/log"
        )

    def test_empty_string_passthrough(self) -> None:
        assert Settings._migrate_run_args_value("") == ""

    def test_multi_element_list_joined(self) -> None:
        result = Settings._migrate_run_args_value(
            ["-logfile", "/path/to/log", "-savedatafolder=/path"]
        )
        assert result == "-logfile /path/to/log -savedatafolder=/path"

    def test_comma_separated_single_element(self) -> None:
        result = Settings._migrate_run_args_value(
            ["-logfile,/path/to/log,-popupwindow"]
        )
        assert result == "-logfile /path/to/log -popupwindow"

    def test_already_correct_single_element(self) -> None:
        result = Settings._migrate_run_args_value(["-logfile /path -popupwindow"])
        assert result == "-logfile /path -popupwindow"

    def test_command_placeholder_preserved(self) -> None:
        result = Settings._migrate_run_args_value(
            ["PROTON_LOG=1 gamemoderun %command% -logfile /tmp/log"]
        )
        assert result == "PROTON_LOG=1 gamemoderun %command% -logfile /tmp/log"

    def test_none_returns_empty(self) -> None:
        assert Settings._migrate_run_args_value(None) == ""

    def test_non_list_non_str_returns_empty(self) -> None:
        assert Settings._migrate_run_args_value(42) == ""
