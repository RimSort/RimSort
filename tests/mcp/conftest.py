"""Fixture helpers for the MCP server tests.

The tests drive the real :class:`MetadataController` against a synthetic RimWorld
installation, so the sorting and validation behavior under test is the
production one rather than a mock of it.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.controllers.metadata_controller import MetadataController
from app.controllers.metadata_db_controller import AuxMetadataController
from app.mcp.core import RimSortMcpCore
from app.models.instance import Instance
from app.models.settings import Settings
from tests.game_layout_fixtures import GameInstall, make_game_install


def write_mod(
    mods_path: Path,
    folder: str,
    package_id: str,
    *,
    rules: str = "",
    versions: tuple[str, ...] = ("1.7",),
    description: str = "A mod used by the RimSort MCP tests.",
    authors: tuple[str, ...] = ("Test Author",),
) -> Path:
    """Write a minimal but realistic mod with ``About/About.xml``.

    :param mods_path: Mods folder to create the mod in
    :param folder: Folder name for the mod
    :param package_id: ``packageId`` to declare
    :param rules: Extra XML inserted before ``</ModMetaData>``
    :param versions: ``supportedVersions`` entries
    :param description: Mod description text
    :param authors: Mod authors
    :return: The created mod folder
    """
    mod_dir = mods_path / folder
    about = mod_dir / "About"
    about.mkdir(parents=True)
    version_xml = "".join(f"<li>{version}</li>" for version in versions)
    author_xml = "".join(f"<li>{author}</li>" for author in authors)
    (about / "About.xml").write_text(
        f"<ModMetaData><name>{folder}</name><packageId>{package_id}</packageId>"
        f"<authors>{author_xml}</authors>"
        f"<supportedVersions>{version_xml}</supportedVersions>"
        f"<description>{description}</description>{rules}</ModMetaData>",
        encoding="utf-8",
    )
    return mod_dir


def write_mods_config(
    config_folder: Path,
    active_ids: list[str],
    *,
    version: str = "1.7.4976 rev1043",
    known_expansions: list[str] | None = None,
) -> Path:
    """Write a ``ModsConfig.xml`` in RimWorld's own shape."""
    config_folder.mkdir(parents=True, exist_ok=True)
    active = "".join(f"<li>{package_id}</li>" for package_id in active_ids)
    expansions = "".join(
        f"<li>{package_id}</li>" for package_id in (known_expansions or [])
    )
    path = config_folder / "ModsConfig.xml"
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        f"<ModsConfigData><version>{version}</version>"
        f"<activeMods>{active}</activeMods>"
        f"<knownExpansions>{expansions}</knownExpansions></ModsConfigData>",
        encoding="utf-8",
    )
    return path


def build_core(settings: Settings) -> RimSortMcpCore:
    """Wire settings to a freshly refreshed :class:`RimSortMcpCore`.

    :param settings: Settings whose active instance points at real folders
    :return: Core object with populated metadata
    """
    from app.utils.steam.steamcmd.wrapper import SteamcmdInterface

    mock_steamcmd = MagicMock(spec=SteamcmdInterface)
    mock_steamcmd.steamcmd_appworkshop_acf_path = ""
    with patch.object(SteamcmdInterface, "instance", return_value=mock_steamcmd):
        metadata_db_controller = AuxMetadataController.get_or_create_cached_instance(
            settings.aux_db_path
        )
        metadata_controller = MetadataController(
            settings,
            lambda: settings.instances[settings.current_instance],
            metadata_db_controller,
        )
        metadata_controller.reset_paths()
        metadata_controller.metadata_mediator.refresh_metadata(
            prefer_versioned=True, case_insensitive_about_xml=True
        )
    return RimSortMcpCore(settings, metadata_controller)


@pytest.fixture
def game_install(tmp_path: Path) -> GameInstall:
    """A synthetic RimWorld install with Core, Royalty and Odyssey content."""
    return make_game_install(
        tmp_path / "RimWorld", "linux", dlcs=("Royalty", "Odyssey")
    )


@pytest.fixture
def config_folder(tmp_path: Path) -> Path:
    """Config folder used as the instance's ``ModsConfig.xml`` location."""
    folder = tmp_path / "Config"
    folder.mkdir()
    return folder


@pytest.fixture
def make_settings(game_install: GameInstall, config_folder: Path) -> Settings:
    """Settings whose active instance is bound to the synthetic install."""
    settings = Settings()
    settings.instances[settings.current_instance] = Instance(
        name=settings.current_instance,
        game_folder=str(game_install.launch_location),
        config_folder=str(config_folder),
        local_folder=str(game_install.mods_path),
        workshop_folder="",
    )
    return settings


@pytest.fixture
def mcp_core(make_settings: Settings) -> Generator[RimSortMcpCore]:
    """A :class:`RimSortMcpCore` bound to a real, refreshed metadata store."""
    yield build_core(make_settings)
    MetadataController._instance = None
