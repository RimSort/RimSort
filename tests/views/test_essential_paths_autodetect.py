# tests/views/test_essential_paths_autodetect.py
"""Tests for silent first-run autodetection of essential paths.

MainContent.check_if_essential_paths_are_set() now tries to auto-fill
missing essential paths (via PathAutodetectService) before prompting the
user, so a GOG/Heroic installation configures itself on first launch.
"""

import types
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from app.utils.system_info import SystemInfo
from app.views import main_content_panel as mcp_module
from app.views.main_content_panel import MainContent


@pytest.fixture
def empty_instance_main_content(
    main_content: tuple[MainContent, list[bool]],
) -> tuple[MainContent, object, object]:
    """MainContent whose current instance has all paths cleared."""
    mc, _save_calls = main_content
    # The shared fixture stubs the essential-paths check; restore the real
    # method because these tests exercise it directly.
    mc.check_if_essential_paths_are_set = types.MethodType(
        MainContent.check_if_essential_paths_are_set, mc
    )
    instance = mc.settings.instances[mc.settings.current_instance]
    instance.game_folder = ""
    instance.config_folder = ""
    instance.local_folder = ""
    instance.workshop_folder = ""
    return mc, instance, mc.settings


def _make_gog_layout(tmp_path: Path) -> tuple[Path, Path]:
    """Create an existing game bundle (with Mods) and a config directory."""
    game_dir = tmp_path / "RimWorld.app"
    (game_dir / "Mods").mkdir(parents=True)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return game_dir, config_dir


def _patch_autodetect(
    monkeypatch: pytest.MonkeyPatch,
    game_dir,
    config_dir,
    workshop_dir,
) -> MagicMock:
    """Point MainContent's PathAutodetectService/SystemInfo at test data."""
    service = MagicMock()
    service.get_darwin_paths.return_value = (game_dir, config_dir, workshop_dir)
    service.get_linux_paths.return_value = (game_dir, config_dir, workshop_dir)
    service.get_windows_paths.return_value = (game_dir, config_dir, workshop_dir)

    service_factory = MagicMock(return_value=service)

    system_info = MagicMock()
    system_info.return_value.operating_system = SystemInfo.OperatingSystem.MACOS
    system_info.OperatingSystem = SystemInfo.OperatingSystem

    monkeypatch.setattr(mcp_module, "PathAutodetectService", service_factory)
    monkeypatch.setattr(mcp_module, "SystemInfo", system_info)
    return service


class TestSilentEssentialAutodetect:
    """Tests for MainContent._autodetect_missing_essential_paths()."""

    def test_fills_only_missing_paths_and_saves(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
        empty_instance_main_content,
    ) -> None:
        mc, instance, settings = empty_instance_main_content
        # Simulate a GOG-like install: game bundle with Mods, no workshop.
        game_dir, config_dir = _make_gog_layout(tmp_path)
        _patch_autodetect(monkeypatch, game_dir, config_dir, tmp_path / "missing_ws")
        save_mock = Mock()
        monkeypatch.setattr(settings, "save", save_mock)

        changed = mc._autodetect_missing_essential_paths()

        assert changed is True
        assert instance.game_folder == str(game_dir)
        assert instance.config_folder == str(config_dir)
        assert instance.local_folder == str(game_dir / "Mods")
        # Non-existent workshop path must not be filled
        assert instance.workshop_folder == ""
        save_mock.assert_called_once()

    def test_never_overwrites_existing_values(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
        empty_instance_main_content,
    ) -> None:
        mc, instance, settings = empty_instance_main_content
        instance.game_folder = "/manually/chosen/game"
        game_dir, config_dir = _make_gog_layout(tmp_path)
        _patch_autodetect(monkeypatch, game_dir, config_dir, tmp_path / "ws")
        monkeypatch.setattr(settings, "save", Mock())

        mc._autodetect_missing_essential_paths()

        # Existing value must win over the auto-detected one
        assert instance.game_folder == "/manually/chosen/game"
        assert instance.config_folder == str(config_dir)
        assert instance.local_folder == str(game_dir / "Mods")

    def test_no_fill_when_detected_paths_do_not_exist(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
        empty_instance_main_content,
    ) -> None:
        mc, instance, settings = empty_instance_main_content
        _patch_autodetect(
            monkeypatch,
            tmp_path / "no_game",
            tmp_path / "no_config",
            tmp_path / "no_ws",
        )
        save_mock = Mock()
        monkeypatch.setattr(settings, "save", save_mock)

        changed = mc._autodetect_missing_essential_paths()

        assert changed is False
        assert instance.game_folder == ""
        assert instance.config_folder == ""
        assert instance.local_folder == ""
        save_mock.assert_not_called()


class TestEssentialCheckUsesAutodetect:
    """check_if_essential_paths_are_set() should try autodetection first."""

    def test_completes_without_dialog_when_autodetect_fills_paths(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_dialogue: Mock,
        tmp_path,
        empty_instance_main_content,
    ) -> None:
        mc, _instance, _settings = empty_instance_main_content
        game_dir, config_dir = _make_gog_layout(tmp_path)
        _patch_autodetect(monkeypatch, game_dir, config_dir, tmp_path / "ws")

        result = mc.check_if_essential_paths_are_set(prompt=True)

        assert result is True
        mock_dialogue.assert_not_called()

    def test_prompts_when_autodetect_finds_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_dialogue: Mock,
        tmp_path,
        empty_instance_main_content,
    ) -> None:
        mc, _instance, _settings = empty_instance_main_content
        _patch_autodetect(
            monkeypatch,
            tmp_path / "no_game",
            tmp_path / "no_config",
            tmp_path / "no_ws",
        )
        mock_dialogue.reset_mock()

        result = mc.check_if_essential_paths_are_set(prompt=True)

        assert result is False
        mock_dialogue.assert_called_once()

    def test_no_autodetect_without_prompt(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_dialogue: Mock,
        tmp_path,
        empty_instance_main_content,
    ) -> None:
        """prompt=False (e.g. deliberate path clearing) must not re-fill paths."""
        mc, instance, _settings = empty_instance_main_content
        game_dir, config_dir = _make_gog_layout(tmp_path)
        _patch_autodetect(monkeypatch, game_dir, config_dir, tmp_path / "ws")

        result = mc.check_if_essential_paths_are_set(prompt=False)

        assert result is False
        assert instance.game_folder == ""
