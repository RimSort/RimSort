from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

from app.controllers.settings_controller import SettingsController
from app.controllers.settings_tabs.locations_tab_controller import (
    LocationsTabController,
)
from app.utils.system_info import SystemInfo
from app.views.settings_dialog import SettingsDialog
from tests.game_layout_fixtures import make_game_install


def _controller(game_folder: Path) -> SettingsController:
    controller = SettingsController.__new__(SettingsController)
    untyped_controller = cast(Any, controller)
    untyped_controller.settings = SimpleNamespace(
        current_instance="default",
        instances={"default": SimpleNamespace(game_folder=str(game_folder))},
    )
    untyped_controller.tr = lambda text, *args: text
    return controller


def test_local_mods_validation_accepts_same_folder_with_different_spelling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game_folder = make_game_install(tmp_path / "RimWorld", "linux").launch_location
    monkeypatch.chdir(tmp_path)
    is_valid, error = _controller(game_folder)._validate_local_mods_location(
        str(Path("RimWorld") / "Mods")
    )
    assert is_valid
    assert error == ""


def test_local_mods_validation_rejects_different_existing_folder(
    tmp_path: Path,
) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")
    other_folder = tmp_path / "OtherMods"
    other_folder.mkdir()
    is_valid, error = _controller(
        install.launch_location
    )._validate_local_mods_location(str(other_folder))
    assert not is_valid
    assert "Mods" in error


def test_local_mods_validation_rejects_folder_when_identity_check_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install = make_game_install(tmp_path / "RimWorld", "linux")

    def raise_os_error(_self: Path, _other: Path) -> bool:
        raise OSError("identity unavailable")

    monkeypatch.setattr(Path, "samefile", raise_os_error)
    is_valid, error = _controller(
        install.launch_location
    )._validate_local_mods_location(str(install.mods_path))
    assert not is_valid
    assert "Mods" in error


def test_local_mods_validation_accepts_sibling_and_workaround_symlink(
    tmp_path: Path,
) -> None:
    install = make_game_install(tmp_path / "RimWorld", "mac-sibling")
    controller = _controller(install.launch_location)
    assert controller._validate_local_mods_location(str(install.mods_path)) == (
        True,
        "",
    )
    link = install.launch_location / "Mods"
    link.symlink_to(install.mods_path, target_is_directory=True)
    assert controller._validate_local_mods_location(str(link)) == (True, "")


def test_unresolved_content_keeps_explicit_existing_local_folder(
    tmp_path: Path,
) -> None:
    game = tmp_path / "RimWorld"
    game.mkdir()
    (game / "RimWorld").write_bytes(b"game")
    (game / "RimWorld").chmod(0o755)
    local = tmp_path / "SelectedMods"
    local.mkdir()
    controller = _controller(game)
    assert controller._validate_game_location(str(game)) == (True, "")
    assert controller._validate_local_mods_location(str(local)) == (True, "")
    assert not controller._validate_local_mods_location(str(local / "missing"))[0]


def test_unresolved_content_diagnostic_names_checked_location(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(tmp_path)
    warnings: list[dict[str, object]] = []

    def capture_warning(**kwargs: object) -> None:
        warnings.append(kwargs)

    monkeypatch.setattr(
        "app.controllers.settings_controller.show_warning", capture_warning
    )
    controller._warn_unresolved_game_content(str(tmp_path))
    assert len(warnings) == 1
    assert str(tmp_path) in str(warnings[0]["details"])


@pytest.mark.parametrize("resolved", [True, False])
def test_choosing_game_uses_derived_mods_or_keeps_explicit_path(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    resolved: bool,
) -> None:
    install = make_game_install(tmp_path / "RimWorld", "mac-sibling")
    if not resolved:
        from shutil import rmtree

        rmtree(install.data_path)
    controller = LocationsTabController.__new__(LocationsTabController)
    controller._validate_game_location = lambda path: (True, "")
    controller._path_selected_callback = lambda path: None
    dialog = MagicMock(spec=SettingsDialog)
    dialog.local_mods_folder_location = QLineEdit("existing explicit path")
    monkeypatch.setattr(
        "app.controllers.settings_tabs.locations_tab_controller.show_dialogue_file",
        lambda **kwargs: str(install.launch_location),
    )
    assert controller._on_game_choose(dialog) == str(install.launch_location)
    assert dialog.local_mods_folder_location.text() == (
        str(install.mods_path) if resolved else "existing explicit path"
    )


@pytest.mark.parametrize("resolved", [True, False])
def test_settings_autodetect_derives_mods_from_retained_game(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    resolved: bool,
) -> None:
    selected = make_game_install(tmp_path / "Selected", "linux")
    if not resolved:
        (selected.content_root / "Version.txt").unlink()
        (selected.data_path / "Core/About/About.xml").unlink()
    detected = make_game_install(tmp_path / "Detected", "mac-sibling")
    controller = _controller(selected.launch_location)
    dialog = MagicMock(spec=SettingsDialog)
    for field in (
        "game_location",
        "config_folder_location",
        "steam_mods_folder_location",
        "local_mods_folder_location",
    ):
        setattr(dialog, field, QLineEdit())
    dialog.game_location.setText(str(selected.launch_location))
    monkeypatch.setattr(controller, "settings_dialog", dialog, raising=False)
    system = MagicMock()
    system.OperatingSystem = SystemInfo.OperatingSystem
    system.return_value.operating_system = SystemInfo.OperatingSystem.MACOS
    monkeypatch.setattr("app.controllers.settings_controller.SystemInfo", system)
    detector = MagicMock()
    detector.get_darwin_paths.return_value = (
        detected.launch_location,
        tmp_path / "config",
        tmp_path / "workshop",
    )
    monkeypatch.setattr(
        "app.controllers.settings_controller.PathAutodetectService", lambda: detector
    )
    controller._on_locations_autodetect_button_clicked()
    assert dialog.game_location.text() == str(selected.launch_location)
    assert dialog.local_mods_folder_location.text() == (
        str(selected.mods_path) if resolved else ""
    )
