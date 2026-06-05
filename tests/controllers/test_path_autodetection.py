from pathlib import Path

from app.controllers.settings_controller import SettingsController


class TestFindSteamRoot:
    """Tests for SettingsController._find_steam_root()."""

    def test_returns_first_valid_candidate_with_steamapps(self, tmp_path: Path) -> None:
        candidate = tmp_path / ".steam" / "steam"
        candidate.mkdir(parents=True)
        (candidate / "steamapps").mkdir()

        result = SettingsController._find_steam_root([candidate])
        assert result == candidate

    def test_returns_first_valid_candidate_with_vdf(self, tmp_path: Path) -> None:
        candidate = tmp_path / ".steam" / "steam"
        (candidate / "config").mkdir(parents=True)
        (candidate / "config" / "libraryfolders.vdf").touch()

        result = SettingsController._find_steam_root([candidate])
        assert result == candidate

    def test_skips_nonexistent_candidates(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does_not_exist"
        valid = tmp_path / "valid_steam"
        valid.mkdir()
        (valid / "steamapps").mkdir()

        result = SettingsController._find_steam_root([nonexistent, valid])
        assert result == valid

    def test_skips_candidates_without_steamapps_or_vdf(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = SettingsController._find_steam_root([empty_dir])
        assert result is None

    def test_returns_none_when_no_candidates_match(self, tmp_path: Path) -> None:
        result = SettingsController._find_steam_root([tmp_path / "a", tmp_path / "b"])
        assert result is None

    def test_respects_priority_order(self, tmp_path: Path) -> None:
        first = tmp_path / "first"
        first.mkdir()
        (first / "steamapps").mkdir()

        second = tmp_path / "second"
        second.mkdir()
        (second / "steamapps").mkdir()

        result = SettingsController._find_steam_root([first, second])
        assert result == first

    def test_returns_none_for_empty_list(self) -> None:
        result = SettingsController._find_steam_root([])
        assert result is None
