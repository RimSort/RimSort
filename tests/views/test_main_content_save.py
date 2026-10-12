from pathlib import Path
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree

import pytest
from PySide6.QtWidgets import QMessageBox

from app.models.metadata.metadata_factory import create_listed_mod_from_path
from app.services.import_export_service import ExportData, ImportExportService
from app.utils.event_bus import EventBus
from app.views import dialogue
from app.views.main_content_panel import MainContent
from tests.game_layout_fixtures import make_game_install, make_mods_config


@pytest.fixture
def history_spy() -> MagicMock:
    return MagicMock()


@pytest.fixture
def save_context(
    main_content: tuple[MainContent, list[bool]],
    history_spy: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MainContent, Path, MagicMock]:
    mc, _calls = main_content
    install = make_game_install(tmp_path / "RimWorld", "linux")
    config_dir = tmp_path / "Config"
    config_dir.mkdir()
    config = make_mods_config(
        config_dir / "ModsConfig.xml", ["ludeon.rimworld", "ludeon.rimworld.royalty"]
    )
    instance = mc.settings.instances[mc.settings.current_instance]
    instance.game_folder = str(install.launch_location)
    instance.config_folder = str(config_dir)
    metadata = MagicMock()
    core = install.data_path / "Core"
    valid, mod = create_listed_mod_from_path(
        core, "1.7", install.mods_path, install.content_root, None
    )
    assert valid
    metadata.mods_metadata = {str(core): mod}
    metadata.game_version = "1.7.4976"
    metadata.get_mods_from_list.return_value = ([str(core)], ["inactive"], {}, {})
    monkeypatch.setattr(mc, "metadata_controller", metadata)
    service = ImportExportService(metadata, mc.settings)
    monkeypatch.setattr(
        service,
        "collect_active_mods",
        lambda uuids, duplicate_mods: ExportData(active_mods=["ludeon.rimworld"]),
    )
    monkeypatch.setattr(mc, "_import_export_service", service)
    monkeypatch.setattr(mc, "_modlist_history_service", history_spy)
    monkeypatch.setattr(mc.settings, "save", MagicMock())
    mc.settings.modlist_history_enabled = True
    mc.settings.active_mods_dividers = [{"uuid": "previous-divider"}]
    mc.active_mods_uuids_last_save = ["previous-saved"]
    mc.active_mods_uuids_restore_state = ["previous-active"]
    mc.inactive_mods_uuids_restore_state = ["previous-inactive"]
    return mc, config, metadata


def assert_save_state_unchanged(mc: MainContent, history_spy: MagicMock) -> None:
    assert mc.active_mods_uuids_last_save == ["previous-saved"]
    assert mc.active_mods_uuids_restore_state == ["previous-active"]
    assert mc.inactive_mods_uuids_restore_state == ["previous-inactive"]
    assert mc.settings.active_mods_dividers == [{"uuid": "previous-divider"}]
    history_spy.write_snapshot.assert_not_called()


def test_cancel_preserves_original_list_and_state(
    save_context: tuple[MainContent, Path, MagicMock],
    history_spy: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc, config, _metadata = save_context
    original = config.read_bytes()
    confirm = MagicMock(return_value=False)
    monkeypatch.setattr(
        dialogue, "confirm_content_discovery_override", confirm, raising=False
    )
    stopped: list[bool] = []
    EventBus().do_save_button_animation_stop.connect(lambda: stopped.append(True))
    assert MainContent._do_save(mc) is False
    assert confirm.call_args.kwargs["action_text"] == "Save anyway"
    assert config.read_bytes() == original
    assert_save_state_unchanged(mc, history_spy)
    assert stopped == [True]


def test_real_save_warning_supports_qobject_controller(
    save_context: tuple[MainContent, Path, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc, _config, _metadata = save_context
    monkeypatch.setattr(QMessageBox, "exec", lambda box: 0)
    assert mc._confirm_official_content_save() is False


def test_explicit_override_saves_only_proposed_ids(
    save_context: tuple[MainContent, Path, MagicMock],
    history_spy: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc, config, _metadata = save_context
    confirm = MagicMock(return_value=True)
    monkeypatch.setattr(
        dialogue, "confirm_content_discovery_override", confirm, raising=False
    )
    assert MainContent._do_save(mc) is True
    confirm.assert_called_once()
    root = ElementTree.parse(config).getroot()
    assert [element.text for element in root.findall("activeMods/li")] == [
        "ludeon.rimworld"
    ]
    assert mc.active_mods_uuids_last_save == mc.active_mods_uuids_restore_state
    history_spy.write_snapshot.assert_called_once()


def test_safe_save_allows_intentionally_disabling_discovered_dlc(
    save_context: tuple[MainContent, Path, MagicMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc, config, metadata = save_context
    game = Path(mc.settings.instances[mc.settings.current_instance].game_folder)
    install = make_game_install(game, "linux", dlcs=("Royalty",))
    royalty = install.data_path / "Royalty"
    valid, mod = create_listed_mod_from_path(
        royalty, "1.7", install.mods_path, install.content_root, None
    )
    assert valid
    metadata.mods_metadata[str(royalty)] = mod
    confirm = MagicMock()
    monkeypatch.setattr(
        dialogue, "confirm_content_discovery_override", confirm, raising=False
    )
    assert MainContent._do_save(mc) is True
    confirm.assert_not_called()
    assert [
        item.text for item in ElementTree.parse(config).findall("activeMods/li")
    ] == ["ludeon.rimworld"]


@pytest.mark.parametrize("field", ["game_folder", "config_folder"])
def test_unconfigured_save_cannot_write_via_cwd_or_stale_metadata(
    save_context: tuple[MainContent, Path, MagicMock],
    history_spy: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    mc, config, _metadata = save_context
    original = config.read_bytes()
    setattr(mc.settings.instances[mc.settings.current_instance], field, "")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        dialogue,
        "confirm_content_discovery_override",
        lambda **kwargs: True,
        raising=False,
    )
    assert MainContent._do_save(mc) is False
    assert config.read_bytes() == original
    assert not (tmp_path / "ModsConfig.xml").exists()
    assert_save_state_unchanged(mc, history_spy)


def test_actual_xml_write_failure_does_not_advance_saved_state(
    save_context: tuple[MainContent, Path, MagicMock],
    history_spy: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mc, config, _metadata = save_context
    make_mods_config(config, ["ludeon.rimworld"])
    original = config.read_bytes()
    monkeypatch.setattr(
        dialogue,
        "confirm_content_discovery_override",
        lambda **kwargs: True,
        raising=False,
    )
    with patch(
        "app.utils.xml.open", side_effect=PermissionError("denied"), create=True
    ):
        assert MainContent._do_save(mc) is False
    assert config.read_bytes() == original
    assert_save_state_unchanged(mc, history_spy)
