from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.controllers.settings_controller import SettingsController
from app.controllers.settings_tabs.locations_tab_controller import (
    LocationsTabController,
)
from app.models.settings import Settings
from app.utils.system_info import SystemInfo
from app.views.settings_dialog import SettingsDialog
from tests.game_layout_fixtures import make_game_install


@pytest.fixture
def game_chooser(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[LocationsTabController, SettingsDialog, list[str]]:
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", MagicMock(return_value=("", ""))
    )
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", MagicMock(return_value=""))
    monkeypatch.setattr(QMessageBox, "information", MagicMock())
    settings = Settings()
    validator = SettingsController.__new__(SettingsController)
    QObject.__init__(validator)
    validator.settings = settings
    dialog = SettingsDialog()
    dialog.game_location.setText("original game")
    dialog.local_mods_folder_location.setText("original mods")
    selected: list[str] = []
    controller = LocationsTabController(
        settings,
        dialog,
        validate_game_location=validator._validate_game_location,
        validate_config_folder_location=validator._validate_config_folder_location,
        validate_local_mods_location=validator._validate_local_mods_location,
        on_path_selected=selected.append,
        on_autodetect=MagicMock(),
        on_instance_folder_choose=MagicMock(),
        on_instance_folder_clear=MagicMock(),
    )
    controller.connect_signals()
    return controller, dialog, selected


def _set_platform(monkeypatch: pytest.MonkeyPatch, system: str) -> None:
    operating_system = {
        "Darwin": SystemInfo.OperatingSystem.MACOS,
        "Windows": SystemInfo.OperatingSystem.WINDOWS,
        "Linux": SystemInfo.OperatingSystem.LINUX,
    }[system]
    monkeypatch.setattr("platform.system", lambda: system)
    monkeypatch.setattr(SystemInfo(), "_operating_system", operating_system)


@pytest.mark.parametrize("bundle_name", ["RimWorldMac.app", "RimWorld.app"])
@pytest.mark.parametrize("layout", ["mac-internal", "mac-sibling"])
def test_choose_macos_bundle_updates_game_and_resolved_mods(
    game_chooser: tuple[LocationsTabController, SettingsDialog, list[str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bundle_name: str,
    layout: str,
) -> None:
    _, dialog, selected = game_chooser
    _set_platform(monkeypatch, "Darwin")
    install = make_game_install(tmp_path / "Steam Library/RimWorld", layout)
    bundle = install.launch_location.rename(
        install.launch_location.with_name(bundle_name)
    )
    mods = bundle / "Mods" if layout == "mac-internal" else install.mods_path
    file_picker = MagicMock(return_value=(str(bundle), ""))
    directory_picker = MagicMock(return_value=str(bundle.parent))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", file_picker)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", directory_picker)

    dialog.game_location_choose_button.click()

    assert dialog.game_location.text() == str(bundle)
    assert dialog.local_mods_folder_location.text() == str(mods)
    assert selected == [str(bundle)]
    file_picker.assert_called_once()
    directory_picker.assert_not_called()


@pytest.mark.parametrize("system", ["Windows", "Linux"])
def test_other_platforms_choose_installation_directory(
    game_chooser: tuple[LocationsTabController, SettingsDialog, list[str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    system: str,
) -> None:
    _, dialog, selected = game_chooser
    _set_platform(monkeypatch, system)
    install = make_game_install(tmp_path / "RimWorld", system.lower())
    directory_picker = MagicMock(return_value=str(install.launch_location))
    file_picker = MagicMock(return_value=("", ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", directory_picker)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", file_picker)

    dialog.game_location_choose_button.click()

    assert dialog.game_location.text() == str(install.launch_location)
    assert dialog.local_mods_folder_location.text() == str(install.mods_path)
    assert selected == [str(install.launch_location)]
    directory_picker.assert_called_once()
    file_picker.assert_not_called()


@pytest.mark.parametrize("system", ["Darwin", "Windows", "Linux"])
def test_cancel_keeps_existing_paths(
    game_chooser: tuple[LocationsTabController, SettingsDialog, list[str]],
    monkeypatch: pytest.MonkeyPatch,
    system: str,
) -> None:
    _, dialog, selected = game_chooser
    _set_platform(monkeypatch, system)

    dialog.game_location_choose_button.click()

    assert dialog.game_location.text() == "original game"
    assert dialog.local_mods_folder_location.text() == "original mods"
    assert selected == []


@pytest.mark.parametrize("selection", ["file", "parent"])
def test_invalid_macos_selection_keeps_existing_paths(
    game_chooser: tuple[LocationsTabController, SettingsDialog, list[str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selection: str,
) -> None:
    _, dialog, selected = game_chooser
    _set_platform(monkeypatch, "Darwin")
    install = make_game_install(tmp_path / "RimWorld", "mac-internal")
    invalid = install.content_root / "Version.txt" if selection == "file" else tmp_path
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", MagicMock(return_value=(str(invalid), ""))
    )
    warning = MagicMock()
    monkeypatch.setattr(QMessageBox, "information", warning)

    dialog.game_location_choose_button.click()

    assert dialog.game_location.text() == "original game"
    assert dialog.local_mods_folder_location.text() == "original mods"
    assert selected == []
    warning.assert_called_once()
