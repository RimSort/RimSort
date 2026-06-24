import json
import shutil
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import msgspec
import pytest

from app.controllers.metadata_controller import MetadataController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.models.instance import Instance
from app.models.metadata.metadata_structure import (
    AboutXmlMod,
    CaseInsensitiveStr,
    ModType,
    SteamDbSchema,
)
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
        mock_settings.external_no_version_warning_metadata_source = "Disabled"
        mock_settings.external_no_version_warning_repo_path = ""
        mock_settings.external_use_this_instead_file_path = ""
        mock_settings.external_use_this_instead_metadata_source = "Disabled"
        mock_settings.external_use_this_instead_repo_path = ""
        mock_settings.prefer_versioned_about_tags = True
        mock_settings.database_expiry = 0
        mock_settings.case_insensitive_about_xml_lookup = True

        yield mock_settings


@pytest.fixture
def mock_settings_dialog() -> MagicMock:
    return MagicMock(spec=SettingsDialog)


@pytest.fixture()
def mock_active_instance() -> MagicMock:
    instance = MagicMock(spec=Instance)
    instance.game_folder = ""
    instance.local_folder = ""
    instance.workshop_folder = ""
    return instance


@pytest.fixture()
def temp_db(tmp_path: Path) -> Generator[AuxMetadataController, None, None]:
    db_path = tmp_path / "test_metadata.db"
    controller = AuxMetadataController(db_path)
    yield controller


@pytest.fixture()
def metadata_controller(
    mock_settings: Settings,
    mock_active_instance: MagicMock,
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
        return MetadataController(mock_settings, lambda: mock_active_instance, temp_db)


def test_metadata_controller_creation(metadata_controller: MetadataController) -> None:
    assert metadata_controller.metadata_mediator is not None
    assert metadata_controller.metadata_db_controller is not None
    assert metadata_controller.steamcmd_wrapper is not None


@pytest.fixture
def metadata_controller_p(
    metadata_controller: MetadataController,
    mock_active_instance: MagicMock,
) -> MetadataController:
    metadata_controller.settings.external_steam_metadata_file_path = (
        "tests/data/dbs/steamDB.json"
    )
    mock_active_instance.game_folder = "tests/data/mod_examples/RimWorld"
    mock_active_instance.local_folder = "tests/data/mod_examples/Local"
    mock_active_instance.workshop_folder = "tests/data/mod_examples/Steam"

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
    assert aux_metadata.published_file_id == "123456789"
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
    assert aux_metadata.published_file_id == "1111"
    assert aux_metadata.acf_time_updated > 0
    assert aux_metadata.acf_time_touched > 0


@pytest.fixture
def metadata_controller_with_steamdb(
    metadata_controller_p: MetadataController,
) -> MetadataController:
    """metadata_controller_p with Steam DB source enabled."""
    metadata_controller_p.settings.external_steam_metadata_source = (
        "Configured file path"
    )
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
    """Verify empty dict returned and cached when steam DB is not loaded."""
    metadata_controller_p.refresh_metadata()
    result1 = metadata_controller_p.steamdb_packageid_to_name
    result2 = metadata_controller_p.steamdb_packageid_to_name
    assert result1 == {}
    assert result2 == {}
    assert result1 is result2


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


def test_get_mod_name_from_package_id_found_in_metadata(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify name resolution from parsed mod metadata."""
    metadata_controller_p.refresh_metadata()
    name = metadata_controller_p.get_mod_name_from_package_id("steam.mod1")
    assert name == "steam mod 1"


def test_get_mod_name_from_package_id_not_found(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify fallback to package ID when mod is not found anywhere."""
    metadata_controller_p.refresh_metadata()
    name = metadata_controller_p.get_mod_name_from_package_id("nonexistent.mod.id")
    assert name == "nonexistent.mod.id"


def test_get_mod_name_from_package_id_case_insensitive(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify lookup is case-insensitive."""
    metadata_controller_p.refresh_metadata()
    name_lower = metadata_controller_p.get_mod_name_from_package_id("steam.mod1")
    name_mixed = metadata_controller_p.get_mod_name_from_package_id("Steam.Mod1")
    assert name_lower == name_mixed
    assert name_lower == "steam mod 1"


def test_workshop_acf_path_property(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify workshop_acf_path is derived from workshop_mods_path."""
    metadata_controller_p.refresh_metadata()
    acf_path = metadata_controller_p.workshop_acf_path
    assert acf_path is not None
    assert acf_path.name == "appworkshop_294100.acf"


def test_workshop_acf_path_when_no_workshop(
    metadata_controller: MetadataController,
) -> None:
    """Verify workshop_acf_path returns None when workshop is not configured."""
    metadata_controller._get_active_instance().workshop_folder = ""
    metadata_controller.reset_paths()
    acf_path = metadata_controller.workshop_acf_path
    assert acf_path is None


def test_acf_data_populated_after_refresh(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify ACF data dicts are populated during refresh."""
    metadata_controller_p.refresh_metadata()
    assert isinstance(metadata_controller_p.steamcmd_acf_data, dict)
    assert len(metadata_controller_p.steamcmd_acf_data) > 0
    assert isinstance(metadata_controller_p.workshop_acf_data, dict)
    assert len(metadata_controller_p.workshop_acf_data) > 0


def test_acf_data_empty_before_refresh(
    metadata_controller: MetadataController,
) -> None:
    """Verify ACF data dicts are empty before refresh."""
    assert metadata_controller.steamcmd_acf_data == {}
    assert metadata_controller.workshop_acf_data == {}


def test_user_rules_property(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify user_rules delegates to mediator."""
    metadata_controller_p.refresh_metadata()
    result = metadata_controller_p.user_rules
    assert result is metadata_controller_p.metadata_mediator.user_rules


# ---- Task 1: Path-based lookup helpers ----


def test_get_mod_returns_mod_for_known_path(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify get_mod returns ListedMod for a populated path."""
    metadata_controller_p.refresh_metadata()
    mod = metadata_controller_p.get_mod(
        Path("tests/data/mod_examples/Steam/steam_mod_1")
    )
    assert mod is not None
    assert mod.name == "steam mod 1"


def test_get_mod_returns_none_for_unknown_path(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify get_mod returns None for an unknown path."""
    metadata_controller_p.refresh_metadata()
    mod = metadata_controller_p.get_mod("tests/data/mod_examples/Steam/nonexistent_mod")
    assert mod is None


def test_get_mod_accepts_path_object(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify get_mod works with Path objects (converted to str internally)."""
    metadata_controller_p.refresh_metadata()
    mod = metadata_controller_p.get_mod(
        Path("tests/data/mod_examples/Steam/steam_mod_1")
    )
    assert mod is not None
    assert mod.name == "steam mod 1"


def test_has_mod_true_for_known_path(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify has_mod returns True for a populated path."""
    metadata_controller_p.refresh_metadata()
    assert metadata_controller_p.has_mod(
        Path("tests/data/mod_examples/Steam/steam_mod_1")
    )


def test_has_mod_false_for_unknown_path(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify has_mod returns False for an unknown path."""
    metadata_controller_p.refresh_metadata()
    assert not metadata_controller_p.has_mod(
        "tests/data/mod_examples/Steam/nonexistent_mod"
    )


def test_has_mod_accepts_path_object(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify has_mod works with Path objects."""
    metadata_controller_p.refresh_metadata()
    assert metadata_controller_p.has_mod(
        Path("tests/data/mod_examples/Steam/steam_mod_1")
    )


def test_resolve_about_xml_to_mod_path_valid(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify resolve_about_xml_to_mod_path finds the mod from About.xml path."""
    metadata_controller_p.refresh_metadata()
    result = metadata_controller_p.resolve_about_xml_to_mod_path(
        str(Path("tests/data/mod_examples/Steam/steam_mod_1/About/About.xml"))
    )
    assert result == str(Path("tests/data/mod_examples/Steam/steam_mod_1"))


def test_resolve_about_xml_to_mod_path_unknown(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify resolve_about_xml_to_mod_path returns None for unknown mods."""
    metadata_controller_p.refresh_metadata()
    result = metadata_controller_p.resolve_about_xml_to_mod_path(
        "tests/data/mod_examples/Steam/nonexistent/About/About.xml"
    )
    assert result is None


# ---- Task 2: DB path properties ----


def test_steam_db_path_when_disabled(
    metadata_controller: MetadataController,
) -> None:
    """Verify steam_db_path returns None when Steam DB is disabled."""
    assert metadata_controller.steam_db_path is None


def test_community_rules_path_when_disabled(
    metadata_controller: MetadataController,
) -> None:
    """Verify community_rules_path returns None when community rules are disabled."""
    assert metadata_controller.community_rules_path is None


def test_steam_db_path_when_configured(
    metadata_controller_with_steamdb: MetadataController,
) -> None:
    """Verify steam_db_path returns a Path when Steam DB is configured."""
    metadata_controller_with_steamdb.reset_paths()
    result = metadata_controller_with_steamdb.steam_db_path
    assert result is not None
    assert isinstance(result, Path)
    assert result.name == "steamDB.json"


def test_community_rules_path_when_configured(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify community_rules_path returns a Path when community rules are configured."""
    metadata_controller_p.settings.external_community_rules_metadata_source = (
        "Configured file path"
    )
    metadata_controller_p.settings.external_community_rules_file_path = (
        "tests/data/dbs/communityRules.json"
    )
    metadata_controller_p.reset_paths()
    result = metadata_controller_p.community_rules_path
    assert result is not None
    assert isinstance(result, Path)
    assert result.name == "communityRules.json"


# ---- Task 3: steamcmd_acf_path property ----


def test_steamcmd_acf_path_property(
    metadata_controller: MetadataController,
) -> None:
    """Verify steamcmd_acf_path delegates to steamcmd_wrapper."""
    result = metadata_controller.steamcmd_acf_path
    assert isinstance(result, str)
    assert "appworkshop_294100.acf" in result


def test_delete_mod_emits_signal(
    metadata_controller_p: MetadataController,
    qtbot: Any,
) -> None:
    """Verify delete_mod emits mod_deleted_signal for each deleted path."""
    metadata_controller_p.refresh_metadata()

    steam_mod_1_path = Path("tests/data/mod_examples/Steam/steam_mod_1")
    emitted: list[str] = []
    metadata_controller_p.mod_deleted_signal.connect(emitted.append)

    metadata_controller_p.delete_mod(steam_mod_1_path)
    assert emitted == [str(steam_mod_1_path)]


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


# ---- Task 4: set_steam_db_blacklist mutation method ----


def test_set_steam_db_blacklist_adds_entry(
    metadata_controller_with_steamdb: MetadataController,
    tmp_path: Path,
) -> None:
    """Verify blacklisting a known PFID updates both in-memory struct and disk."""
    mc = metadata_controller_with_steamdb
    mc.refresh_metadata()

    # Redirect persistence to a temp file
    src = Path("tests/data/dbs/steamDB.json")
    dest = tmp_path / "steamDB.json"
    shutil.copy(src, dest)
    mc.metadata_mediator.steam_db_path = dest

    known_pfid = "basic_mod1-multiversion-multiauthor-nodependencies"
    result = mc.set_steam_db_blacklist(
        known_pfid, blacklisted=True, comment="test reason"
    )
    assert result is True

    # Verify in-memory
    assert mc.steam_db is not None
    entry = mc.steam_db.database[known_pfid]
    assert entry.blacklist.value is True
    assert entry.blacklist.comment == "test reason"

    # Verify on disk
    disk_data = msgspec.json.decode(dest.read_bytes(), type=SteamDbSchema)
    disk_entry = disk_data.database[known_pfid]
    assert disk_entry.blacklist.value is True
    assert disk_entry.blacklist.comment == "test reason"


def test_set_steam_db_blacklist_creates_entry_for_unknown_pfid(
    metadata_controller_with_steamdb: MetadataController,
    tmp_path: Path,
) -> None:
    """Verify blacklisting an unknown PFID creates a new entry."""
    mc = metadata_controller_with_steamdb
    mc.refresh_metadata()

    dest = tmp_path / "steamDB.json"
    shutil.copy(Path("tests/data/dbs/steamDB.json"), dest)
    mc.metadata_mediator.steam_db_path = dest

    new_pfid = "999999999"
    assert mc.steam_db is not None
    assert new_pfid not in mc.steam_db.database

    result = mc.set_steam_db_blacklist(new_pfid, blacklisted=True, comment="spam mod")
    assert result is True

    # Verify entry was created in memory
    assert new_pfid in mc.steam_db.database
    entry = mc.steam_db.database[new_pfid]
    assert entry.blacklist.value is True
    assert entry.blacklist.comment == "spam mod"

    # Verify entry exists on disk
    disk_data = msgspec.json.decode(dest.read_bytes(), type=SteamDbSchema)
    assert new_pfid in disk_data.database
    assert disk_data.database[new_pfid].blacklist.value is True


def test_set_steam_db_blacklist_clears_entry(
    metadata_controller_with_steamdb: MetadataController,
    tmp_path: Path,
) -> None:
    """Verify clearing blacklist resets it to defaults."""
    mc = metadata_controller_with_steamdb
    mc.refresh_metadata()

    dest = tmp_path / "steamDB.json"
    shutil.copy(Path("tests/data/dbs/steamDB.json"), dest)
    mc.metadata_mediator.steam_db_path = dest

    pfid = "basic_mod1-multiversion-multiauthor-nodependencies"

    # First blacklist it
    mc.set_steam_db_blacklist(pfid, blacklisted=True, comment="blocked")
    assert mc.steam_db is not None
    assert mc.steam_db.database[pfid].blacklist.value is True

    # Then clear it
    result = mc.set_steam_db_blacklist(pfid, blacklisted=False)
    assert result is True

    # Verify in-memory: defaults mean value=False, comment=""
    entry = mc.steam_db.database[pfid]
    assert entry.blacklist.value is False
    assert entry.blacklist.comment == ""

    # Verify on disk: blacklist should be omitted (omit_defaults=True)
    disk_data = msgspec.json.decode(dest.read_bytes(), type=SteamDbSchema)
    assert disk_data.database[pfid].blacklist.value is False


def test_set_steam_db_blacklist_returns_false_when_no_db(
    metadata_controller_p: MetadataController,
) -> None:
    """Verify returns False when no steam DB is loaded."""
    mc = metadata_controller_p
    # Steam DB is disabled in metadata_controller_p (source = "Disabled")
    mc.refresh_metadata()
    assert mc.steam_db is None

    result = mc.set_steam_db_blacklist("12345", blacklisted=True, comment="test")
    assert result is False


def test_set_steam_db_blacklist_persists_to_disk(
    metadata_controller_with_steamdb: MetadataController,
    tmp_path: Path,
) -> None:
    """Verify the JSON file written to disk is valid and contains the update."""
    mc = metadata_controller_with_steamdb
    mc.refresh_metadata()

    dest = tmp_path / "steamDB.json"
    shutil.copy(Path("tests/data/dbs/steamDB.json"), dest)
    mc.metadata_mediator.steam_db_path = dest

    pfid = "basic_mod4-multiversion-singleauthor-nodependencies"
    mc.set_steam_db_blacklist(pfid, blacklisted=True, comment="reason here")

    # Verify disk file is valid JSON with expected structure
    raw = json.loads(dest.read_text())
    assert "version" in raw
    assert "database" in raw
    assert isinstance(raw["version"], int)
    assert raw["version"] > 0

    # Verify the specific entry
    assert pfid in raw["database"]
    assert raw["database"][pfid]["blacklist"]["value"] is True
    assert raw["database"][pfid]["blacklist"]["comment"] == "reason here"

    # Verify version was updated with expiry offset
    # The version should be roughly time.time() + database_expiry
    import time

    expected_min = int(time.time()) - 10  # allow some slack
    assert raw["version"] >= expected_min


def test_process_creation_adds_mod_to_metadata(
    metadata_controller: MetadataController, tmp_path: Path
) -> None:
    """process_creation should parse a mod and add it to mods_metadata."""
    mod_path = tmp_path / "test_mod"
    mod_path.mkdir()
    about_dir = mod_path / "About"
    about_dir.mkdir()
    (about_dir / "About.xml").write_text(
        "<ModMetaData><name>Test Mod</name><packageId>test.mod</packageId></ModMetaData>"
    )

    metadata_controller.metadata_mediator.local_mods_path = tmp_path
    metadata_controller.metadata_mediator.game_path = tmp_path
    metadata_controller.metadata_mediator._game_version = "1.5"
    metadata_controller.metadata_mediator._mods_metadata = {}

    metadata_controller.process_creation("local", str(mod_path))
    assert str(mod_path) in metadata_controller.mods_metadata


def test_process_deletion_removes_mod(
    metadata_controller: MetadataController, tmp_path: Path
) -> None:
    """process_deletion should remove a mod from mods_metadata."""
    mod_path = str(tmp_path / "test_mod")
    from app.models.metadata.metadata_structure import ListedMod

    metadata_controller.metadata_mediator._mods_metadata = {}
    mock_mod = MagicMock(spec=ListedMod)
    metadata_controller.metadata_mediator._mods_metadata[mod_path] = mock_mod

    metadata_controller.process_deletion("local", mod_path)
    assert mod_path not in metadata_controller.mods_metadata


def test_process_update_refreshes_metadata(
    metadata_controller: MetadataController, tmp_path: Path
) -> None:
    """process_update should re-parse a mod and update mods_metadata."""
    mod_path = tmp_path / "test_mod"
    mod_path.mkdir()
    about_dir = mod_path / "About"
    about_dir.mkdir()
    (about_dir / "About.xml").write_text(
        "<ModMetaData><name>Original Name</name><packageId>test.mod</packageId></ModMetaData>"
    )

    metadata_controller.metadata_mediator.local_mods_path = tmp_path
    metadata_controller.metadata_mediator.game_path = tmp_path
    metadata_controller.metadata_mediator._game_version = "1.5"
    metadata_controller.metadata_mediator._mods_metadata = {}

    metadata_controller.process_creation("local", str(mod_path))
    assert metadata_controller.mods_metadata[str(mod_path)].name == "Original Name"

    (about_dir / "About.xml").write_text(
        "<ModMetaData><name>Updated Name</name><packageId>test.mod</packageId></ModMetaData>"
    )
    metadata_controller.process_update("local", str(mod_path))
    assert metadata_controller.mods_metadata[str(mod_path)].name == "Updated Name"


# ---- Task 4: get_mods_from_list ----


def _make_about_xml_mod(
    name: str,
    package_id: str,
    mod_type: ModType,
    mod_path: str | None = None,
) -> AboutXmlMod:
    """Helper to create an AboutXmlMod with the given properties.

    mod_type setter is write-once (from UNKNOWN), so we set it immediately.
    mod_path setter is also write-once; we bypass it via _mod_path to avoid
    side-effects on published_file_id cached_property.
    """
    mod = AboutXmlMod(name=name, package_id=CaseInsensitiveStr(package_id))
    mod.mod_type = mod_type
    if mod_path is not None:
        mod._mod_path = Path(mod_path)
    return mod


def test_get_mods_from_list_happy_path(
    metadata_controller: MetadataController,
) -> None:
    """Given a list of package IDs, return correct active/inactive split."""
    mod_a = _make_about_xml_mod("Mod A", "author.moda", ModType.LOCAL, "/mods/mod_a")
    mod_b = _make_about_xml_mod("Mod B", "author.modb", ModType.LOCAL, "/mods/mod_b")
    mod_c = _make_about_xml_mod("Mod C", "author.modc", ModType.LOCAL, "/mods/mod_c")

    metadata_controller.metadata_mediator._mods_metadata = {
        "/mods/mod_a": mod_a,
        "/mods/mod_b": mod_b,
        "/mods/mod_c": mod_c,
    }

    active, inactive, duplicates, missing = metadata_controller.get_mods_from_list(
        ["author.modA", "author.modC"]  # case-insensitive
    )

    assert active == ["/mods/mod_a", "/mods/mod_c"]
    assert "/mods/mod_b" in inactive
    assert "/mods/mod_a" not in inactive
    assert "/mods/mod_c" not in inactive
    assert duplicates == {}
    assert missing == []


def test_get_mods_from_list_missing_mods(
    metadata_controller: MetadataController,
) -> None:
    """Package IDs not in metadata appear in the missing list."""
    mod_a = _make_about_xml_mod("Mod A", "author.moda", ModType.LOCAL, "/mods/mod_a")

    metadata_controller.metadata_mediator._mods_metadata = {
        "/mods/mod_a": mod_a,
    }

    active, inactive, duplicates, missing = metadata_controller.get_mods_from_list(
        ["author.modA", "nonexistent.mod"]
    )

    assert active == ["/mods/mod_a"]
    assert "nonexistent.mod" in missing
    assert len(missing) == 1


def test_get_mods_from_list_duplicate_resolution(
    metadata_controller: MetadataController,
) -> None:
    """When duplicate mods exist, resolve by source priority (default: Ludeon > Local > Workshop)."""
    # Same package ID, different sources
    mod_local = _make_about_xml_mod(
        "Core Local", "ludeon.rimworld", ModType.LOCAL, "/mods/local/core"
    )
    mod_ludeon = _make_about_xml_mod(
        "Core Ludeon", "ludeon.rimworld", ModType.LUDEON, "/mods/ludeon/core"
    )
    mod_workshop = _make_about_xml_mod(
        "Core Workshop",
        "ludeon.rimworld",
        ModType.STEAM_WORKSHOP,
        "/mods/workshop/core",
    )

    metadata_controller.metadata_mediator._mods_metadata = {
        "/mods/local/core": mod_local,
        "/mods/ludeon/core": mod_ludeon,
        "/mods/workshop/core": mod_workshop,
    }

    active, inactive, duplicates, missing = metadata_controller.get_mods_from_list(
        ["Ludeon.RimWorld"]
    )

    # Should pick Ludeon source (highest priority in default order)
    assert active == ["/mods/ludeon/core"]
    assert "/mods/local/core" in inactive
    assert "/mods/workshop/core" in inactive
    assert "ludeon.rimworld" in duplicates
    assert len(duplicates["ludeon.rimworld"]) == 3
    assert missing == []


def test_get_mods_from_list_steam_suffix_priority(
    metadata_controller: MetadataController,
) -> None:
    """The _steam suffix triggers Steam Workshop priority for duplicate resolution."""
    mod_local = _make_about_xml_mod(
        "My Mod Local", "author.mymod", ModType.LOCAL, "/mods/local/mymod"
    )
    mod_workshop = _make_about_xml_mod(
        "My Mod Workshop",
        "author.mymod",
        ModType.STEAM_WORKSHOP,
        "/mods/workshop/mymod",
    )

    metadata_controller.metadata_mediator._mods_metadata = {
        "/mods/local/mymod": mod_local,
        "/mods/workshop/mymod": mod_workshop,
    }

    active, inactive, duplicates, missing = metadata_controller.get_mods_from_list(
        ["author.mymod_steam"]
    )

    # _steam suffix => SOURCE_PRIORITY_STEAM: Workshop > Local
    assert active == ["/mods/workshop/mymod"]
    assert "/mods/local/mymod" in inactive
    assert missing == []


def test_get_mods_from_list_no_duplicates_single_mod(
    metadata_controller: MetadataController,
) -> None:
    """When a package ID has only one mod, no duplicate resolution is needed."""
    mod_a = _make_about_xml_mod(
        "Mod A", "author.moda", ModType.STEAM_WORKSHOP, "/mods/mod_a"
    )

    metadata_controller.metadata_mediator._mods_metadata = {
        "/mods/mod_a": mod_a,
    }

    active, inactive, duplicates, missing = metadata_controller.get_mods_from_list(
        ["author.modA"]
    )

    assert active == ["/mods/mod_a"]
    assert inactive == []
    assert duplicates == {}
    assert missing == []


def test_get_mods_from_list_empty_list(
    metadata_controller: MetadataController,
) -> None:
    """An empty package ID list should produce all mods as inactive."""
    mod_a = _make_about_xml_mod("Mod A", "author.moda", ModType.LOCAL, "/mods/mod_a")

    metadata_controller.metadata_mediator._mods_metadata = {
        "/mods/mod_a": mod_a,
    }

    active, inactive, duplicates, missing = metadata_controller.get_mods_from_list([])

    assert active == []
    assert inactive == ["/mods/mod_a"]
    assert missing == []


# ---- Local mods path derivation ----


def test_reset_paths_derives_local_mods_from_game_when_empty(
    metadata_controller: MetadataController,
) -> None:
    """When local_folder is empty but game_folder is set, local_mods_path is derived as game_path / 'Mods'."""
    metadata_controller._get_active_instance().game_folder = (
        "tests/data/mod_examples/RimWorld"
    )
    metadata_controller._get_active_instance().local_folder = ""

    metadata_controller.reset_paths()

    assert metadata_controller.metadata_mediator.local_mods_path == Path(
        "tests/data/mod_examples/RimWorld/Mods"
    )


def test_reset_paths_preserves_explicit_local_folder(
    metadata_controller: MetadataController,
) -> None:
    """An explicitly set local_folder is NOT overwritten by derivation."""
    metadata_controller._get_active_instance().game_folder = (
        "tests/data/mod_examples/RimWorld"
    )
    metadata_controller._get_active_instance().local_folder = (
        "tests/data/mod_examples/Local"
    )

    metadata_controller.reset_paths()

    assert metadata_controller.metadata_mediator.local_mods_path == Path(
        "tests/data/mod_examples/Local"
    )


def test_reset_paths_leaves_local_mods_none_when_no_game(
    metadata_controller: MetadataController,
) -> None:
    """When both game_folder and local_folder are empty, local_mods_path stays None."""
    metadata_controller._get_active_instance().game_folder = ""
    metadata_controller._get_active_instance().local_folder = ""

    metadata_controller.reset_paths()

    assert metadata_controller.metadata_mediator.local_mods_path is None
