from pathlib import Path
from unittest.mock import MagicMock
from xml.etree import ElementTree

import pytest

from app.controllers.metadata_controller import MetadataController
from app.controllers.sort_controller import Sorter
from app.models.instance import Instance
from app.models.metadata.metadata_mediator import MetadataMediator
from app.models.metadata.metadata_structure import AboutXmlMod, CompiledDependencyData
from app.models.settings import Settings
from app.services.import_export_service import ImportExportService
from app.services.mod_list_parser import parse_mod_list_file
from app.utils.constants import RIMWORLD_PACKAGE_IDS, SortMethod
from tests.game_layout_fixtures import make_game_install, make_mods_config


def _local_mod(folder: Path, package_id: str, rules: str = "") -> None:
    about = folder / "About"
    about.mkdir(parents=True)
    (about / "About.xml").write_text(
        f"<ModMetaData><name>{folder.name}</name><packageId>{package_id}</packageId>"
        f"<supportedVersions><li>1.7</li></supportedVersions>{rules}</ModMetaData>",
        encoding="utf-8",
    )


@pytest.mark.parametrize("kind", ["mac-sibling", "linux"])
def test_discover_sort_save_17_without_enabling_disabled_dlc(
    tmp_path: Path, kind: str
) -> None:
    install = make_game_install(
        tmp_path / "RimWorld",
        kind,
        dlcs=("Royalty", "Ideology", "Biotech", "Anomaly", "Odyssey"),
    )
    _local_mod(install.mods_path / "Harmony", "brrainz.harmony")
    _local_mod(
        install.mods_path / "TestMod",
        "test.author.mod",
        "<loadAfterByVersion><v1.7><li>ludeon.rimworld.biotech</li></v1.7></loadAfterByVersion>",
    )
    mediator = MetadataMediator(
        tmp_path / "rules.json",
        None,
        None,
        None,
        install.mods_path,
        install.launch_location,
    )
    mediator.refresh_metadata()
    by_id = {
        str(mod.package_id): path
        for path, mod in mediator.mods_metadata.items()
        if isinstance(mod, AboutXmlMod)
    }
    assert set(RIMWORLD_PACKAGE_IDS) <= set(by_id)
    assert mediator.game_version.startswith("1.7.")
    expected_ids = [
        "brrainz.harmony",
        "ludeon.rimworld",
        "ludeon.rimworld.royalty",
        "ludeon.rimworld.ideology",
        "ludeon.rimworld.biotech",
        "test.author.mod",
    ]
    config_dir = tmp_path / "Config"
    config_dir.mkdir()
    config = make_mods_config(
        config_dir / "ModsConfig.xml", list(reversed(expected_ids))
    )
    active_ids = parse_mod_list_file(str(config)).package_ids
    compiled = CompiledDependencyData.build(mediator.mods_metadata, False)
    success, sorted_paths = Sorter(
        SortMethod.TOPOLOGICAL,
        compiled,
        mediator.mods_metadata,
        {by_id[package_id] for package_id in active_ids},
    ).sort()
    assert success
    settings = Settings()
    settings.instances[settings.current_instance] = Instance(
        game_folder=str(install.launch_location),
        config_folder=str(config_dir),
        local_folder=str(install.mods_path),
    )
    metadata = MagicMock(spec=MetadataController)
    metadata.game_version = mediator.game_version
    metadata.get_mod.side_effect = mediator.mods_metadata.get
    service = ImportExportService(metadata, settings)
    exported = service.collect_active_mods(sorted_paths)
    service.save_to_mods_config(exported.active_mods)
    assert parse_mod_list_file(str(config)).package_ids == expected_ids
    root = ElementTree.parse(config).getroot()
    assert root.findtext("version") == mediator.game_version
    assert {item.text for item in root.findall("knownExpansions/li")} == set(
        RIMWORLD_PACKAGE_IDS
    ) - {"ludeon.rimworld"}
