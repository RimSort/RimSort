import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.controllers.todds_controller import ToddsController


@pytest.fixture
def settings_controller(tmp_path: Path) -> MagicMock:
    controller = MagicMock()
    instance = MagicMock()
    instance.local_folder = str(tmp_path / "local_mods")
    instance.workshop_folder = str(tmp_path / "workshop")
    controller.settings.instances = {"Default": instance}
    controller.settings.current_instance = "Default"
    controller.settings.todds_active_mods_target = False
    controller.settings.todds_preset = "optimized"
    controller.settings.todds_dry_run = False
    controller.settings.todds_overwrite = False
    controller.settings.todds_custom_command = ""
    return controller


@pytest.fixture
def metadata_controller() -> MagicMock:
    return MagicMock()


@pytest.fixture
def active_mods_setup(
    settings_controller: MagicMock, metadata_controller: MagicMock, tmp_path: Path
) -> tuple[MagicMock, MagicMock]:
    """Setup for active mods mode tests."""
    settings_controller.settings.todds_active_mods_target = True

    mod_dir = tmp_path / "mods" / "MyMod"
    mod_dir.mkdir(parents=True)
    settings_controller._test_mod_dir = str(mod_dir)

    return settings_controller, metadata_controller


class TestGenerateToddsTxt:
    def test_all_mods_mode_writes_existing_dirs(
        self,
        settings_controller: MagicMock,
        metadata_controller: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When todds_active_mods_target is False, writes local and workshop folders."""
        (tmp_path / "local_mods").mkdir()
        (tmp_path / "workshop").mkdir()

        tc = ToddsController(
            settings=settings_controller.settings,
            metadata_controller=metadata_controller,
        )
        path, count = tc.generate_todds_txt()

        assert count == 2
        assert os.path.exists(path)
        with open(path) as f:
            lines = f.read().strip().split("\n")
        assert len(lines) == 2

    def test_all_mods_mode_skips_missing_dirs(
        self,
        settings_controller: MagicMock,
        metadata_controller: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When directories don't exist, they are skipped."""
        tc = ToddsController(
            settings=settings_controller.settings,
            metadata_controller=metadata_controller,
        )
        path, count = tc.generate_todds_txt()
        assert count == 0

    def test_active_mods_mode_writes_mod_paths(
        self, active_mods_setup: tuple[MagicMock, MagicMock]
    ) -> None:
        """When todds_active_mods_target is True, writes individual mod paths."""
        settings_controller, metadata_controller = active_mods_setup

        tc = ToddsController(
            settings=settings_controller.settings,
            metadata_controller=metadata_controller,
        )
        path, count = tc.generate_todds_txt(
            active_mod_paths=[settings_controller._test_mod_dir]
        )
        assert count == 1

    def test_active_mods_mode_skips_divider_paths(
        self, active_mods_setup: tuple[MagicMock, MagicMock]
    ) -> None:
        """Divider paths (starting with __divider__) are skipped."""
        settings_controller, metadata_controller = active_mods_setup

        tc = ToddsController(
            settings=settings_controller.settings,
            metadata_controller=metadata_controller,
        )
        path, count = tc.generate_todds_txt(
            active_mod_paths=[
                "__divider__test123",
                settings_controller._test_mod_dir,
            ]
        )
        assert count == 1


class TestActiveModPathsGuard:
    def test_generate_todds_txt_returns_zero_when_paths_missing(
        self, settings_controller: MagicMock, metadata_controller: MagicMock
    ) -> None:
        """When todds_active_mods_target is True but active_mod_paths is None, returns 0."""
        settings_controller.settings.todds_active_mods_target = True
        tc = ToddsController(
            settings=settings_controller.settings,
            metadata_controller=metadata_controller,
        )
        _, count = tc.generate_todds_txt(active_mod_paths=None)
        assert count == 0
