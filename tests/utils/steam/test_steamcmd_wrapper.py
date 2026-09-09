from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.steam.steamcmd.wrapper import SteamcmdInterface


def test_console_log_path() -> None:
    iface = SteamcmdInterface.__new__(SteamcmdInterface)
    iface.steamcmd_install_path = "/steamcmd"
    assert iface.console_log_path == Path("/steamcmd/logs/console_log.txt")


def test_process_environment_is_unchanged_outside_linux(tmp_path: Path) -> None:
    iface = SteamcmdInterface.__new__(SteamcmdInterface)
    iface.system = "Windows"
    iface.steamcmd_prefix = str(tmp_path)

    assert iface._get_process_environment() is None
    assert not (tmp_path / "home").exists()


def test_process_environment_resolves_relative_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    iface = SteamcmdInterface.__new__(SteamcmdInterface)
    iface.system = "Linux"
    iface.steamcmd_prefix = "instance"

    environment = iface._get_process_environment()

    assert environment is not None
    assert environment == {
        "HOME": str(tmp_path / "instance" / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "instance" / "home" / ".config"),
        "XDG_DATA_HOME": str(tmp_path / "instance" / "home" / ".local" / "share"),
    }
    assert Path(environment["HOME"]).is_absolute()


@patch.object(
    SteamcmdInterface, "_build_download_script", return_value="/tmp/script.txt"
)
def test_download_mods_sets_console_log_path(
    mock_build_script: MagicMock, tmp_path: Path
) -> None:
    iface = SteamcmdInterface.__new__(SteamcmdInterface)
    iface.setup = True
    iface.system = "Linux"
    iface.steamcmd_prefix = str(tmp_path)
    iface.steamcmd = "/steamcmd/steamcmd.sh"
    iface.steamcmd_install_path = "/steamcmd"
    iface.steamcmd_steam_path = "/steam/steam"
    iface.validate_downloads = False

    runner = MagicMock()
    runner._pending_steamcmd_batches = []

    iface.download_mods(["12345"], runner)

    assert runner._steamcmd_console_log_path == str(
        Path("/steamcmd/logs/console_log.txt")
    )
    mock_build_script.assert_called_once_with(["12345"])
    runner.execute.assert_called_once_with(
        "/steamcmd/steamcmd.sh",
        ['+runscript "/tmp/script.txt"'],
        1,
        environment={
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "home" / ".config"),
            "XDG_DATA_HOME": str(tmp_path / "home" / ".local" / "share"),
        },
    )
    assert (tmp_path / "home" / ".config").is_dir()
    assert (tmp_path / "home" / ".local" / "share").is_dir()
