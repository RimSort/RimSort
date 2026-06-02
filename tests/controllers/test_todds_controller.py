import os
from pathlib import Path
from unittest.mock import MagicMock, patch

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
def metadata_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def active_mods_setup(
    settings_controller: MagicMock, metadata_manager: MagicMock, tmp_path: Path
) -> tuple[MagicMock, MagicMock]:
    """Setup for active mods mode tests."""
    settings_controller.settings.todds_active_mods_target = True

    mod_dir = tmp_path / "mods" / "MyMod"
    mod_dir.mkdir(parents=True)
    metadata_manager.internal_local_metadata = {
        "uuid-1": {"path": str(mod_dir)},
    }

    return settings_controller, metadata_manager


@pytest.fixture
def todds_runner() -> MagicMock:
    """Create a mock ToddsRunner."""
    runner = MagicMock()
    runner.todds_dry_run_support = False
    return runner


@pytest.fixture
def controller_with_paths(
    settings_controller: MagicMock, metadata_manager: MagicMock, tmp_path: Path
) -> ToddsController:
    """Create a ToddsController with valid directory paths."""
    (tmp_path / "local_mods").mkdir()
    return ToddsController(
        settings_controller=settings_controller,
        metadata_manager=metadata_manager,
    )


class TestGenerateToddsTxt:
    def test_all_mods_mode_writes_existing_dirs(
        self,
        settings_controller: MagicMock,
        metadata_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When todds_active_mods_target is False, writes local and workshop folders."""
        (tmp_path / "local_mods").mkdir()
        (tmp_path / "workshop").mkdir()

        tc = ToddsController(
            settings_controller=settings_controller,
            metadata_manager=metadata_manager,
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
        metadata_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When directories don't exist, they are skipped."""
        tc = ToddsController(
            settings_controller=settings_controller,
            metadata_manager=metadata_manager,
        )
        path, count = tc.generate_todds_txt()
        assert count == 0

    def test_active_mods_mode_writes_mod_paths(
        self, active_mods_setup: tuple[MagicMock, MagicMock]
    ) -> None:
        """When todds_active_mods_target is True, writes individual mod paths."""
        settings_controller, metadata_manager = active_mods_setup

        tc = ToddsController(
            settings_controller=settings_controller,
            metadata_manager=metadata_manager,
        )
        path, count = tc.generate_todds_txt(active_mod_uuids=["uuid-1"])
        assert count == 1

    def test_active_mods_mode_skips_divider_uuids(
        self, active_mods_setup: tuple[MagicMock, MagicMock]
    ) -> None:
        """Divider UUIDs (starting with __divider__) are skipped."""
        settings_controller, metadata_manager = active_mods_setup

        tc = ToddsController(
            settings_controller=settings_controller,
            metadata_manager=metadata_manager,
        )
        path, count = tc.generate_todds_txt(
            active_mod_uuids=["__divider__test123", "uuid-1"]
        )
        assert count == 1


class TestOptimizeTextures:
    def test_optimize_creates_interface_and_executes(
        self, controller_with_paths: ToddsController, todds_runner: MagicMock
    ) -> None:
        """optimize_textures creates a ToddsInterface and calls execute."""
        with patch("app.controllers.todds_controller.ToddsInterface") as MockTI:
            mock_instance = MagicMock()
            MockTI.return_value = mock_instance
            result = controller_with_paths.optimize_textures(todds_runner)

        MockTI.assert_called_once_with(
            preset="optimized",
            dry_run=False,
            overwrite=False,
            custom_command="",
        )
        mock_instance.execute_todds_cmd.assert_called_once()
        assert result is True  # paths_written > 0

    def test_optimize_returns_false_when_no_paths(
        self, settings_controller: MagicMock, metadata_manager: MagicMock
    ) -> None:
        """optimize_textures returns False when no valid paths are found."""
        # Directories don't exist, so 0 paths written
        tc = ToddsController(
            settings_controller=settings_controller,
            metadata_manager=metadata_manager,
        )
        runner = MagicMock()
        result = tc.optimize_textures(runner)
        assert result is False


class TestDeleteDdsTextures:
    def test_delete_uses_clean_preset(
        self, controller_with_paths: ToddsController, todds_runner: MagicMock
    ) -> None:
        """delete_dds_textures creates ToddsInterface with clean preset."""
        with patch("app.controllers.todds_controller.ToddsInterface") as MockTI:
            mock_instance = MagicMock()
            MockTI.return_value = mock_instance
            controller_with_paths.delete_dds_textures(todds_runner)

        MockTI.assert_called_once_with(
            preset="clean",
            dry_run=False,
        )
        mock_instance.execute_todds_cmd.assert_called_once()
