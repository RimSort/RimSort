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
        mock_settings.external_community_rules_metadata_source = "Disabled"
        mock_settings.external_community_rules_repo = ""
        mock_settings.external_steam_metadata_file_path = ""
        mock_settings.external_steam_metadata_source = "Disabled"
        mock_settings.external_steam_metadata_repo = ""
        mock_settings.external_no_version_warning_file_path = ""
        mock_settings.external_use_this_instead_file_path = ""
        mock_settings.prefer_versioned_about_tags = True

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
    controller = AuxMetadataController(db_path)
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


@pytest.fixture
def metadata_controller_with_steamdb(
    metadata_controller_p: MetadataController,
) -> MetadataController:
    """metadata_controller_p with Steam DB source enabled."""
    metadata_controller_p.settings_controller.settings.external_steam_metadata_source = "Configured file path"
    metadata_controller_p.reset_paths()
    return metadata_controller_p


def test_steamdb_packageid_to_name_uses_packageid_not_pfid(
    metadata_controller_with_steamdb: MetadataController,
) -> None:
    """Verify mapping keys are actual packageIds, not published file IDs."""
    metadata_controller_with_steamdb.refresh_metadata()
    mapping = metadata_controller_with_steamdb.steamdb_packageid_to_name
    # The test steamDB.json has entries with packageId like "packageId1",
    # NOT keyed by the dict keys like "basic_mod1-multiversion-..."
    assert "packageid1" in mapping
    assert "basic_mod1-multiversion-multiauthor-nodependencies" not in mapping


def test_steamdb_packageid_to_name_is_cached(
    metadata_controller_with_steamdb: MetadataController,
) -> None:
    """Verify steamdb_packageid_to_name returns the same object on repeated calls."""
    metadata_controller_with_steamdb.refresh_metadata()
    result1 = metadata_controller_with_steamdb.steamdb_packageid_to_name
    result2 = metadata_controller_with_steamdb.steamdb_packageid_to_name
    assert result1 is result2
    assert len(result1) > 0


def test_steamdb_packageid_to_name_empty_when_no_db(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify empty dict returned when steam DB is not loaded (not cached)."""
    metadata_controller_p.refresh_metadata()
    result1 = metadata_controller_p.steamdb_packageid_to_name
    result2 = metadata_controller_p.steamdb_packageid_to_name
    assert result1 == {}
    assert result2 == {}
    # Not cached when DB is None — each call returns a fresh empty dict
    assert result1 is not result2


def test_packageid_to_paths_is_cached(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify packageid_to_paths returns the same object on repeated calls (cached)."""
    metadata_controller_p.refresh_metadata()
    result1 = metadata_controller_p.packageid_to_paths
    result2 = metadata_controller_p.packageid_to_paths
    assert result1 is result2
    assert len(result1) > 0


def test_packageid_to_paths_invalidated_on_refresh(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify cache is invalidated after refresh_metadata()."""
    metadata_controller_p.refresh_metadata()
    result1 = metadata_controller_p.packageid_to_paths
    metadata_controller_p.refresh_metadata()
    result2 = metadata_controller_p.packageid_to_paths
    assert result1 is not result2


def test_steamdb_packageid_to_name_invalidated_on_refresh(
    metadata_controller_with_steamdb: MetadataController,
) -> None:
    """Verify steamdb cache is invalidated after refresh_metadata()."""
    metadata_controller_with_steamdb.refresh_metadata()
    result1 = metadata_controller_with_steamdb.steamdb_packageid_to_name
    metadata_controller_with_steamdb.refresh_metadata()
    result2 = metadata_controller_with_steamdb.steamdb_packageid_to_name
    assert result1 is not result2


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
    metadata_controller_p.delete_mod(local_mod_2_path)
    mod_2, aux_metadata_2 = metadata_controller_p.get_metadata_with_path(
        local_mod_2_path
    )

    assert mod_2 is None
    assert aux_metadata_2 is None
