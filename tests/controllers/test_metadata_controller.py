from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from app.controllers.metadata_controller import MetadataController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.controllers.settings_controller import SettingsController
from app.models.metadata.metadata_structure import AboutXmlMod
from app.models.settings import Settings
from app.utils.app_info import AppInfo
from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.views.settings_dialog import SettingsDialog


@pytest.fixture
def mock_settings() -> Generator[MagicMock, None, None]:
    with (
        patch("app.models.settings.Settings.load") as _,
        patch("app.models.settings.Settings.save") as _,
    ):
        mock_settings = MagicMock(spec=Settings)
        mock_settings.load.return_value = None
        mock_settings.save.return_value = None

        mock_settings.external_community_rules_file_path = ""
        mock_settings.external_steam_metadata_file_path = ""

        yield mock_settings


@pytest.fixture
def mock_settings_dialog() -> MagicMock:
    return MagicMock(spec=SettingsDialog)


@pytest.fixture
def settings_controller(
    mock_settings: Settings,
) -> SettingsController:
    mock_sc = MagicMock(spec=SettingsController)
    mock_sc._update_view_from_model.return_value = None
    mock_sc.settings = mock_settings

    return mock_sc


@pytest.fixture()
def temp_db(tmp_path: Path) -> Generator[AuxMetadataController, None, None]:
    db_path = tmp_path / "test_metadata.db"
    with patch.object(AppInfo, "aux_metadata_db", db_path):
        controller = AuxMetadataController()
        yield controller


@pytest.fixture()
def metadata_controller(
    settings_controller: SettingsController,
    temp_db: AuxMetadataController,
) -> MetadataController:
    with (
        patch.object(SteamcmdInterface, "instance") as steamcmd_instance,
        patch.object(AppInfo, "user_rules_file", Path("tests/data/dbs/userRules.json")),
    ):
        steamcmd_instance.return_value = MagicMock(spec=SteamcmdInterface)
        steamcmd_instance.return_value.steamcmd_appworkshop_acf_path = str(
            (
                Path("tests/data/instance/instance_1/steam")
                / "steamapps"
                / "workshop"
                / "appworkshop_294100.acf"
            )
        )
        return MetadataController(settings_controller, temp_db)


def test_metadata_controller_creation(metadata_controller: MetadataController) -> None:
    assert metadata_controller.metadata_mediator is not None
    assert metadata_controller.metadata_db_controller is not None
    assert metadata_controller.steamcmd_wrapper is not None


@pytest.fixture
def metadata_controller_p(
    metadata_controller: MetadataController,
) -> MetadataController:
    metadata_controller.settings_controller.settings.external_steam_metadata_file_path = "tests/data/dbs/steamDB.json"
    metadata_controller.settings_controller.active_instance.game_folder = (
        "tests/data/mod_examples/RimWorld"
    )
    metadata_controller.settings_controller.active_instance.local_folder = (
        "tests/data/mod_examples/Local"
    )
    metadata_controller.settings_controller.active_instance.workshop_folder = (
        "tests/data/mod_examples/Steam"
    )

    metadata_controller.reset_paths()
    return metadata_controller


def test_metadata_controller_refresh(metadata_controller_p: MetadataController) -> None:
    metadata_controller_p.refresh_metadata()

    assert metadata_controller_p.metadata_mediator.mods_metadata is not None
    assert len(metadata_controller_p.metadata_mediator.mods_metadata) > 0


def test_metadata_controller_get_metadata_with_path(
    metadata_controller_p: MetadataController,
) -> None:
    metadata_controller_p.refresh_metadata()
    steam_mod_1_path = Path("tests/data/mod_examples/Steam/steam_mod_1")
    mod, aux_metadata = metadata_controller_p.get_metadata_with_path(steam_mod_1_path)

    assert mod is not None
    assert aux_metadata is not None
    assert aux_metadata.type == "ModType.STEAM_WORKSHOP"
    assert aux_metadata.published_file_id == 123456789
    assert aux_metadata.acf_time_updated > 0
    assert aux_metadata.acf_time_touched > 0

    rimworld_core_path = Path("tests/data/mod_examples/RimWorld/Data/Core")
    mod, aux_metadata = metadata_controller_p.get_metadata_with_path(rimworld_core_path)

    assert isinstance(mod, AboutXmlMod)
    assert aux_metadata is not None
    assert aux_metadata.type == "ModType.LUDEON"

    assert mod.preview_img_path is not None
    assert mod.preview_img_path.exists()
    assert mod.steam_app_id == 294100

    steamcmd_mod_1_path = Path("tests/data/mod_examples/Local/steamcmd_mod_1")
    mod, aux_metadata = metadata_controller_p.get_metadata_with_path(
        steamcmd_mod_1_path
    )

    assert mod is not None
    assert aux_metadata is not None
    assert aux_metadata.type == "ModType.STEAM_CMD"
    assert aux_metadata.published_file_id == 1111
    assert aux_metadata.acf_time_updated > 0
    assert aux_metadata.acf_time_touched > 0


def test_metadata_controller_delete_mod(
    metadata_controller_p: MetadataController,
) -> None:
    metadata_controller_p.refresh_metadata()

    steam_mod_1_path = Path("tests/data/mod_examples/Steam/steam_mod_1")
    local_mod_2_path = Path("tests/data/mod_examples/Local/local_mod_2")
    mod_1, aux_metadata_1 = metadata_controller_p.get_metadata_with_path(
        steam_mod_1_path
    )
    mod_2, aux_metadata_2 = metadata_controller_p.get_metadata_with_path(
        local_mod_2_path
    )

    assert mod_1 is not None
    assert aux_metadata_1 is not None

    assert mod_2 is not None
    assert aux_metadata_2 is not None

    # Ensure mod_1 is deleted but not mod_2
    metadata_controller_p.delete_mod(steam_mod_1_path)

    mod_1, aux_metadata_1 = metadata_controller_p.get_metadata_with_path(
        steam_mod_1_path
    )
    mod_2, aux_metadata_2 = metadata_controller_p.get_metadata_with_path(
        local_mod_2_path
    )

    assert mod_1 is None
    assert aux_metadata_1 is None

    assert mod_2 is not None
    assert aux_metadata_2 is not None

    # Ensure mod_2 is deleted
    metadata_controller_p.delete_mod(str(local_mod_2_path))
    mod_2, aux_metadata_2 = metadata_controller_p.get_metadata_with_path(
        local_mod_2_path
    )

    assert mod_2 is None
    assert aux_metadata_2 is None
