from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

import pytest

from app.models.metadata.metadata_factory import create_listed_mod_from_path
from app.models.metadata.metadata_structure import ListedMod, ModType
from app.services import official_content_service
from tests.game_layout_fixtures import GameInstall, make_game_install
from tests.game_layout_fixtures import make_mods_config as make_config


def discover_official_mods(install: GameInstall) -> dict[str, ListedMod]:
    mods: dict[str, ListedMod] = {}
    for path in install.data_path.iterdir():
        valid, mod = create_listed_mod_from_path(
            path, "1.7.4976", install.mods_path, install.content_root, None
        )
        assert valid
        mods[str(path)] = mod
    return mods


def test_missing_core_is_reported(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    config = make_config(tmp_path / "ModsConfig.xml", [])
    issues = official_content_service.find_official_content_issues(
        {}, install.launch_location, config
    )
    assert issues.missing_package_ids == ("ludeon.rimworld",)
    assert issues.has_issues
    assert issues.data_path == install.data_path
    assert not issues.config_unreadable


@pytest.mark.parametrize(
    "enabled", ["ludeon.rimworld.royalty", "LUDEON.RIMWORLD.ROYALTY_STEAM"]
)
def test_enabled_missing_dlc_is_reported_case_insensitively(
    tmp_path: Path, enabled: str
) -> None:
    install = make_game_install(tmp_path / "RimWorld", "mac-sibling")
    config = make_config(tmp_path / "ModsConfig.xml", ["ludeon.rimworld", enabled])
    issues = official_content_service.find_official_content_issues(
        discover_official_mods(install), install.launch_location, config
    )
    assert issues.missing_package_ids == ("ludeon.rimworld.royalty",)


@pytest.mark.parametrize(
    "mod_type", [ModType.LOCAL, ModType.STEAM_WORKSHOP, ModType.LUDEON]
)
def test_impostor_outside_selected_data_cannot_satisfy_core(
    tmp_path: Path, mod_type: ModType
) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    mods = discover_official_mods(install)
    core = mods[str(install.data_path / "Core")]
    core._mod_path = tmp_path / "Workshop" / "FakeCore"
    core._mod_type = mod_type
    config = make_config(tmp_path / "ModsConfig.xml", ["ludeon.rimworld"])
    issues = official_content_service.find_official_content_issues(
        mods, install.launch_location, config
    )
    assert issues.missing_package_ids == ("ludeon.rimworld",)


def test_invalid_official_metadata_does_not_satisfy_core(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    mods = discover_official_mods(install)
    mods[str(install.data_path / "Core")].valid = False
    issues = official_content_service.find_official_content_issues(
        mods, install.launch_location, make_config(tmp_path / "ModsConfig.xml", [])
    )
    assert issues.has_issues


@pytest.mark.parametrize(
    "contents",
    [
        "broken xml",
        "<ModsConfigData/>",
        "<ModsConfigData><activeMods><notLi>bad</notLi></activeMods></ModsConfigData>",
    ],
)
def test_uninspectable_existing_list_is_reported(tmp_path: Path, contents: str) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    config = tmp_path / "ModsConfig.xml"
    config.write_text(contents)
    issues = official_content_service.find_official_content_issues(
        discover_official_mods(install), install.launch_location, config
    )
    assert issues.config_unreadable
    assert issues.has_issues


def test_unreadable_existing_list_is_reported(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    mods = discover_official_mods(install)
    config = make_config(tmp_path / "ModsConfig.xml", ["ludeon.rimworld"])
    with patch.object(ElementTree, "parse", side_effect=PermissionError("denied")):
        issues = official_content_service.find_official_content_issues(
            mods, install.launch_location, config
        )
    assert issues.config_unreadable


@pytest.mark.parametrize("dlcs", [(), ("Royalty",)])
def test_discovered_content_and_single_active_item_are_safe(
    tmp_path: Path, dlcs: tuple[str, ...]
) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux", dlcs=dlcs)
    config = make_config(tmp_path / "ModsConfig.xml", ["LUDEON.RIMWORLD"])
    issues = official_content_service.find_official_content_issues(
        discover_official_mods(install), install.launch_location, config
    )
    assert not issues.has_issues


def test_absent_config_is_not_an_unreadable_existing_file(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    issues = official_content_service.find_official_content_issues(
        discover_official_mods(install),
        install.launch_location,
        tmp_path / "missing.xml",
    )
    assert not issues.has_issues
