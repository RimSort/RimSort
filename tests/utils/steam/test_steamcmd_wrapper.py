from pathlib import Path
from unittest.mock import MagicMock, patch

from app.utils.steam.steamcmd.wrapper import SteamcmdInterface


def test_console_log_path() -> None:
    iface = SteamcmdInterface.__new__(SteamcmdInterface)
    iface.steamcmd_install_path = "/steamcmd"
    assert iface.console_log_path == Path("/steamcmd/logs/console_log.txt")


@patch.object(
    SteamcmdInterface, "_build_download_script", return_value="/tmp/script.txt"
)
def test_download_mods_sets_console_log_path(mock_build_script: MagicMock) -> None:
    iface = SteamcmdInterface.__new__(SteamcmdInterface)
    iface.setup = True
    iface.steamcmd = "/steamcmd/steamcmd.exe"
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
        "/steamcmd/steamcmd.exe",
        ['+runscript "/tmp/script.txt"'],
        1,
    )
