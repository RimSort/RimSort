from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from app.models.instance import Instance
from app.models.settings import Settings
from app.services import instance_service
from app.services.instance_service import InstanceService
from tests.game_layout_fixtures import make_game_install


@pytest.mark.parametrize("kind", ["mac-sibling", "mac-internal", "linux", "windows"])
def test_clone_copies_content_once_and_preserves_launch_location(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    install = make_game_install(
        tmp_path / "Source" / "RimWorld", kind, dlcs=("Odyssey",)
    )
    (install.mods_path / "local-mod.txt").write_text("local content")
    if kind == "mac-sibling":
        (install.launch_location / "Mods").symlink_to(
            install.mods_path, target_is_directory=True
        )
    unrelated = tmp_path / "Source" / "unrelated.txt"
    unrelated.write_text("do not copy")
    config = tmp_path / "Config"
    config.mkdir()
    (config / "ModsConfig.xml").write_text("original config")
    destination = tmp_path / "Clone"
    settings = Settings()
    source = Instance(
        name="source",
        game_folder=str(install.launch_location),
        local_folder=str(install.mods_path),
        config_folder=str(config),
        steamcmd_install_path=str(tmp_path / "no-steamcmd"),
    )
    settings.instances = {"source": source}
    settings.current_instance = "source"
    service = InstanceService.__new__(InstanceService)
    service.settings = settings
    service.steamcmd_wrapper = MagicMock()
    bus = MagicMock()
    bus.do_threaded_loading_animation.emit.side_effect = lambda icon, callback, text: (
        callback()
    )
    monkeypatch.setattr(instance_service, "EventBus", lambda: bus)
    monkeypatch.setattr(
        instance_service.QInputDialog, "getText", lambda *args: ("clone", True)
    )
    monkeypatch.setattr(
        instance_service,
        "BinaryChoiceDialog",
        lambda **kwargs: MagicMock(exec_is_positive=lambda: True),
    )
    monkeypatch.setattr(
        instance_service.InstanceController,
        "get_instance_folder_path",
        lambda *args: destination,
    )
    created = MagicMock()
    monkeypatch.setattr(service, "create_new_instance", created)
    before = source.game_folder, source.local_folder
    service.clone_existing_instance("source")
    data = created.call_args.kwargs["instance_data"]
    target_root = destination / install.content_root.name
    target_launch = target_root / install.launch_location.relative_to(
        install.content_root
    )
    assert data["game_folder"] == str(target_launch)
    assert data["local_folder"] == str(target_root / "Mods")
    assert (target_root / "Data" / "Core" / "About" / "About.xml").is_file()
    assert (target_root / "Data" / "Odyssey" / "About" / "About.xml").is_file()
    assert (target_root / "Mods" / "local-mod.txt").read_text() == "local content"
    assert not (target_root / "unrelated.txt").exists()
    assert (source.game_folder, source.local_folder) == before
    assert (install.mods_path / "local-mod.txt").read_text() == "local content"
    assert bus.do_threaded_loading_animation.emit.call_count == 1


def test_unresolved_clone_mapping_does_not_select_a_parent(tmp_path: Path) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    missing_bundle = install.content_root / "Missing.app"
    assert (
        instance_service._get_clone_game_paths(missing_bundle, tmp_path / "Clone")
        is None
    )
