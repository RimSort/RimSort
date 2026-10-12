from pathlib import Path
from shutil import copytree, rmtree

import pytest

from app.controllers.instance_controller import InstanceController
from app.models.instance import Instance
from app.models.metadata.metadata_factory import create_listed_mod_from_path
from app.models.metadata.metadata_mediator import MetadataMediator
from app.models.metadata.metadata_structure import AboutXmlMod, ModType
from app.services.mod_path_service import get_mod_paths, resolve_data_source
from tests.game_layout_fixtures import make_game_install


@pytest.mark.parametrize("kind", ["mac-internal", "mac-sibling", "linux"])
def test_all_data_consumers_use_the_same_content_root(
    tmp_path: Path, kind: str
) -> None:
    install = make_game_install(tmp_path / "RimWorld", kind)
    instance = Instance(
        game_folder=str(install.launch_location),
        local_folder=str(install.mods_path),
        workshop_folder=str(tmp_path / "workshop"),
    )
    core = install.data_path / "Core"
    assert get_mod_paths(instance)[0] == str(install.data_path)
    assert InstanceController.get_game_data_path(instance) == install.data_path
    assert resolve_data_source(instance, str(core)) == "expansion"
    assert resolve_data_source(instance, str(install.mods_path / "local")) == "local"
    assert (
        resolve_data_source(instance, str(tmp_path / "workshop" / "123")) == "workshop"
    )
    valid, mod = create_listed_mod_from_path(
        core, "1.7.4976", install.mods_path, install.launch_location, None
    )
    assert valid
    assert mod.mod_type == ModType.LUDEON


def test_mediator_discovers_sibling_core_and_all_dlcs(tmp_path: Path) -> None:
    install = make_game_install(
        tmp_path / "RimWorld",
        "mac-sibling",
        dlcs=("Royalty", "Ideology", "Biotech", "Anomaly", "Odyssey"),
    )
    local = install.mods_path / "local"
    workshop = tmp_path / "Workshop"
    workshop_mod = workshop / "123"
    copytree(install.data_path / "Core", local)
    copytree(install.data_path / "Core", workshop_mod)
    mediator = MetadataMediator(
        tmp_path / "rules.json",
        None,
        None,
        workshop,
        install.mods_path,
        install.launch_location,
    )
    mediator.refresh_metadata()
    assert mediator.game_version == "1.7.4976 rev1043"
    assert mediator.game_modules_path == install.data_path
    assert mediator.mods_metadata[str(local)].mod_type == ModType.LOCAL
    assert mediator.mods_metadata[str(workshop_mod)].mod_type == ModType.STEAM_WORKSHOP
    assert {
        str(mod.package_id)
        for mod in mediator.mods_metadata.values()
        if isinstance(mod, AboutXmlMod) and mod.mod_type == ModType.LUDEON
    } == {
        "ludeon.rimworld",
        "ludeon.rimworld.royalty",
        "ludeon.rimworld.ideology",
        "ludeon.rimworld.biotech",
        "ludeon.rimworld.anomaly",
        "ludeon.rimworld.odyssey",
    }
    mediator.game_path = tmp_path / "Unresolved.app"
    mediator.refresh_metadata()
    assert mediator.game_version == "Unknown"
    assert mediator.mods_metadata == {}


def test_mediator_does_not_mix_valid_internal_and_sibling_roots(tmp_path: Path) -> None:
    make_game_install(tmp_path / "RimWorld", "mac-sibling", dlcs=("Odyssey",))
    internal = make_game_install(tmp_path / "RimWorld", "mac-internal", "1.6.9999")
    mediator = MetadataMediator(
        tmp_path / "rules.json",
        None,
        None,
        None,
        internal.mods_path,
        internal.launch_location,
    )
    mediator.refresh_metadata()
    assert mediator.game_version == "1.6.9999"
    assert mediator.game_modules_path == internal.data_path
    assert set(mediator.mods_metadata) == {str(internal.data_path / "Core")}


def test_factory_does_not_classify_unvalidated_data_as_official(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux", dlcs=("Royalty",))
    (install.content_root / "Version.txt").unlink()
    rmtree(install.data_path / "Core")
    valid, mod = create_listed_mod_from_path(
        install.data_path / "Royalty",
        "1.7",
        install.mods_path,
        install.launch_location,
        None,
    )
    assert valid
    assert mod.mod_type != ModType.LUDEON


def test_unresolved_data_helpers_do_not_guess_paths(tmp_path: Path) -> None:
    instance = Instance(game_folder=str(tmp_path / "Missing.app"))
    assert InstanceController.get_game_data_path(instance) is None
    assert not any(Path(p).name == "Data" for p in get_mod_paths(instance))
    assert resolve_data_source(instance, str(tmp_path / "Data" / "Core")) is None
