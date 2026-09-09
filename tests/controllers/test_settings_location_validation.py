from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.controllers.settings_controller import SettingsController


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
    game_folder = tmp_path / "RimWorld"
    (game_folder / "Mods").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    is_valid, error = _controller(game_folder)._validate_local_mods_location(
        str(Path("RimWorld") / "Mods")
    )

    assert is_valid
    assert error == ""


def test_local_mods_validation_rejects_different_existing_folder(
    tmp_path: Path,
) -> None:
    game_folder = tmp_path / "RimWorld"
    (game_folder / "Mods").mkdir(parents=True)
    other_folder = tmp_path / "OtherMods"
    other_folder.mkdir()

    is_valid, error = _controller(game_folder)._validate_local_mods_location(
        str(other_folder)
    )

    assert not is_valid
    assert "Mods" in error


def test_local_mods_validation_rejects_folder_when_identity_check_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game_folder = tmp_path / "RimWorld"
    local_mods = game_folder / "Mods"
    local_mods.mkdir(parents=True)

    def raise_os_error(_self: Path, _other: Path) -> bool:
        raise OSError("identity unavailable")

    monkeypatch.setattr(Path, "samefile", raise_os_error)

    is_valid, error = _controller(game_folder)._validate_local_mods_location(
        str(local_mods)
    )

    assert not is_valid
    assert "Mods" in error
