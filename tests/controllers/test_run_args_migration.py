"""
Unit tests for run_args migration logic in SettingsController.

Tests the migration from old comma-separated format to new space-separated format.
"""


def migrate_run_args(run_args: list[str]) -> list[str]:
    """
    Migrate old comma-separated run_args format to new space-separated format.

    This is a standalone copy of SettingsController._migrate_run_args() for testing.

    :param run_args: Current run_args list
    :return: Migrated run_args list in new format
    """
    if not run_args:
        return []

    # Single element - check if it needs migration
    if len(run_args) == 1:
        arg = run_args[0]
        # If it contains commas, migrate from comma-separated to space-separated
        if "," in arg:
            parts = [part.strip() for part in arg.split(",") if part.strip()]
            migrated = " ".join(parts)
            return [migrated]
        # Already in new format (single string, no commas)
        return run_args

    # Multiple elements - join with spaces
    migrated = " ".join(run_args)
    return [migrated]


def test_migrate_empty_list() -> None:
    """Empty list should remain empty."""
    result = migrate_run_args([])
    assert result == []


def test_migrate_multi_element_list() -> None:
    """Multiple elements should be joined with spaces."""
    result = migrate_run_args(["-logfile", "/tmp/log", "-popupwindow"])
    assert result == ["-logfile /tmp/log -popupwindow"]


def test_migrate_comma_separated_string() -> None:
    """Old example: comma-separated string should be converted to space-separated."""
    result = migrate_run_args(
        ["-logfile,/path/to/file.log,-savedatafolder=/path/to/savedata,-popupwindow"]
    )
    assert result == [
        "-logfile /path/to/file.log -savedatafolder=/path/to/savedata -popupwindow"
    ]


def test_migrate_comma_separated_with_spaces() -> None:
    """Comma-separated with extra spaces should be cleaned up."""
    result = migrate_run_args(["-logfile, /path/to/log, -popupwindow"])
    assert result == ["-logfile /path/to/log -popupwindow"]


def test_no_migration_needed_space_separated() -> None:
    """Space-separated format (already new) should not be changed."""
    result = migrate_run_args(["-logfile /tmp/log -popupwindow"])
    assert result == ["-logfile /tmp/log -popupwindow"]


def test_no_migration_needed_with_command_placeholder() -> None:
    """New format with %command% should not be changed."""
    result = migrate_run_args(["%command% -logfile /tmp/log"])
    assert result == ["%command% -logfile /tmp/log"]


def test_no_migration_needed_env_vars() -> None:
    """New format with env vars should not be changed."""
    result = migrate_run_args(["PROTON_LOG=1 %command%"])
    assert result == ["PROTON_LOG=1 %command%"]


def test_migrate_single_arg_no_comma() -> None:
    """Single argument without comma should remain unchanged."""
    result = migrate_run_args(["-popupwindow"])
    assert result == ["-popupwindow"]


def test_migrate_complex_paths() -> None:
    """Migration should handle complex paths correctly."""
    result = migrate_run_args(
        ["-logfile", "/home/user/logs/rimworld.log", "-savedatafolder=/data"]
    )
    assert result == ["-logfile /home/user/logs/rimworld.log -savedatafolder=/data"]


def test_migrate_preserves_arg_format() -> None:
    """Migration should preserve argument format (with = signs, etc)."""
    result = migrate_run_args(["-arg1=value1", "-arg2=value2", "-flag"])
    assert result == ["-arg1=value1 -arg2=value2 -flag"]


def test_migrate_mixed_format_with_paths() -> None:
    """Migration should handle mixed formats with file paths."""
    result = migrate_run_args(["-logfile", "/tmp/rimworld.log", "-popupwindow"])
    assert result == ["-logfile /tmp/rimworld.log -popupwindow"]
