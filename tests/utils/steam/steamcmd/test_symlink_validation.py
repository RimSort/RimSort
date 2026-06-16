import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.steam.steamcmd.wrapper import SteamcmdInterface
from app.utils.symlink import resolve_symlink_target


class TestResolveSymlinkTarget:
    def test_valid_symlink_returns_target(self, tmp_path: Path) -> None:
        target = tmp_path / "target_dir"
        target.mkdir()
        link = tmp_path / "link"
        os.symlink(str(target), str(link))

        result = resolve_symlink_target(str(link))
        assert result == str(target)

    def test_dangling_symlink_returns_none(self, tmp_path: Path) -> None:
        target = tmp_path / "nonexistent"
        link = tmp_path / "link"
        os.symlink(str(target), str(link))

        result = resolve_symlink_target(str(link))
        assert result is None

    def test_not_a_symlink_returns_none(self, tmp_path: Path) -> None:
        regular_dir = tmp_path / "regular"
        regular_dir.mkdir()

        result = resolve_symlink_target(str(regular_dir))
        assert result is None

    def test_nonexistent_path_returns_none(self, tmp_path: Path) -> None:
        result = resolve_symlink_target(str(tmp_path / "nope"))
        assert result is None


@pytest.fixture
def steamcmd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SteamcmdInterface:
    """Create a SteamcmdInterface with paths rooted in tmp_path, bypassing __init__."""
    monkeypatch.setattr(SteamcmdInterface, "_instance", None)
    instance = object.__new__(SteamcmdInterface)
    instance.initialized = True
    instance.setup = True
    instance.steamcmd_prefix = str(tmp_path)
    instance.steamcmd_steam_path = str(tmp_path / "steam")
    instance.steamcmd_content_path = str(
        tmp_path / "steam" / "steamapps" / "workshop" / "content"
    )
    instance.translate = lambda ctx, text: text
    Path(instance.steamcmd_content_path).mkdir(parents=True, exist_ok=True)
    return instance


class TestValidateContentSymlink:
    def test_healthy_symlink_returns_true(
        self, steamcmd: SteamcmdInterface, tmp_path: Path
    ) -> None:
        target = tmp_path / "local_mods"
        target.mkdir()
        link = Path(steamcmd.steamcmd_content_path) / "294100"
        os.symlink(str(target), str(link))

        assert steamcmd.validate_content_symlink(str(target)) is True

    def test_real_directory_returns_true(
        self, steamcmd: SteamcmdInterface
    ) -> None:
        real_dir = Path(steamcmd.steamcmd_content_path) / "294100"
        real_dir.mkdir()

        assert steamcmd.validate_content_symlink(str(real_dir)) is True

    def test_dangling_symlink_shows_dialog_and_returns_false_on_decline(
        self, steamcmd: SteamcmdInterface, tmp_path: Path
    ) -> None:
        gone = tmp_path / "deleted_mods"
        link = Path(steamcmd.steamcmd_content_path) / "294100"
        os.symlink(str(gone), str(link))

        with patch(
            "app.utils.steam.steamcmd.wrapper.BinaryChoiceDialog"
        ) as MockDialog:
            MockDialog.return_value.exec_is_positive.return_value = False
            result = steamcmd.validate_content_symlink(str(tmp_path / "new_mods"))
            assert result is False
            MockDialog.assert_called_once()

    def test_dangling_symlink_recreates_on_accept(
        self, steamcmd: SteamcmdInterface, tmp_path: Path
    ) -> None:
        gone = tmp_path / "deleted_mods"
        new_target = tmp_path / "new_mods"
        new_target.mkdir()
        link = Path(steamcmd.steamcmd_content_path) / "294100"
        os.symlink(str(gone), str(link))

        with patch(
            "app.utils.steam.steamcmd.wrapper.BinaryChoiceDialog"
        ) as MockDialog:
            MockDialog.return_value.exec_is_positive.return_value = True
            steamcmd.create_symlink = MagicMock(return_value=True)
            result = steamcmd.validate_content_symlink(str(new_target))
            assert result is True
            steamcmd.create_symlink.assert_called_once_with(
                str(new_target), str(link), force=True
            )

    def test_missing_symlink_shows_dialog(
        self, steamcmd: SteamcmdInterface, tmp_path: Path
    ) -> None:
        new_target = tmp_path / "mods"
        new_target.mkdir()

        with patch(
            "app.utils.steam.steamcmd.wrapper.BinaryChoiceDialog"
        ) as MockDialog:
            MockDialog.return_value.exec_is_positive.return_value = False
            result = steamcmd.validate_content_symlink(str(new_target))
            assert result is False
