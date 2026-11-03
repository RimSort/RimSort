from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.views.player_log_tab import PlayerLogTab

pytestmark = pytest.mark.usefixtures("mock_metadata_controller")


@pytest.mark.parametrize(
    ("is_waylith", "expected_subdir"),
    [(False, ""), (True, "Logs")],
    ids=["unity_pre_1_7", "waylith_1_7_plus"],
)
def test_get_player_log_path_respects_waylith(
    mock_settings_controller: MagicMock,
    mock_metadata_controller: MagicMock,
    tmp_path: Path,
    is_waylith: bool,
    expected_subdir: str,
) -> None:
    settings = mock_settings_controller.settings
    settings.instances[settings.current_instance].config_folder = str(
        tmp_path / "config"
    )
    mock_metadata_controller.is_waylith = is_waylith

    player_log = tmp_path / expected_subdir / "Player.log"
    player_log.parent.mkdir(parents=True, exist_ok=True)
    player_log.write_text("log")

    tab = PlayerLogTab(settings)

    assert tab._get_player_log_path() == player_log


def test_get_player_log_path_none_when_missing(
    mock_settings_controller: MagicMock,
    mock_metadata_controller: MagicMock,
    tmp_path: Path,
) -> None:
    settings = mock_settings_controller.settings
    settings.instances[settings.current_instance].config_folder = str(
        tmp_path / "config"
    )
    mock_metadata_controller.is_waylith = True

    tab = PlayerLogTab(settings)

    assert tab._get_player_log_path() is None
