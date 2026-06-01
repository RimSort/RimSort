import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from app.utils.ignore_manager import IgnoreManager


@pytest.fixture
def ignore_file(tmp_path: Path) -> Generator[Path]:
    file_path = tmp_path / "ignore.json"
    with patch.object(IgnoreManager, "get_ignore_file_path", return_value=file_path):
        yield file_path


class TestLoadIgnoredMods:
    def test_no_file_returns_empty(self, ignore_file: Path) -> None:
        result = IgnoreManager.load_ignored_mods()
        assert result == set()

    def test_list_format(self, ignore_file: Path) -> None:
        ignore_file.write_text(json.dumps(["mod.a", "mod.b"]))
        result = IgnoreManager.load_ignored_mods()
        assert result == {"mod.a", "mod.b"}

    def test_dict_format(self, ignore_file: Path) -> None:
        data = {"ignored_mods": ["mod.a", "mod.b"], "description": "test"}
        ignore_file.write_text(json.dumps(data))
        result = IgnoreManager.load_ignored_mods()
        assert result == {"mod.a", "mod.b"}

    def test_invalid_json_returns_empty(self, ignore_file: Path) -> None:
        ignore_file.write_text("not json{{{")
        result = IgnoreManager.load_ignored_mods()
        assert result == set()

    def test_invalid_format_returns_empty(self, ignore_file: Path) -> None:
        ignore_file.write_text(json.dumps("just a string"))
        result = IgnoreManager.load_ignored_mods()
        assert result == set()


class TestSaveIgnoredMods:
    def test_saves_sorted_with_metadata(self, ignore_file: Path) -> None:
        result = IgnoreManager.save_ignored_mods({"mod.b", "mod.a"})
        assert result is True
        data = json.loads(ignore_file.read_text())
        assert data["ignored_mods"] == ["mod.a", "mod.b"]
        assert "description" in data

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested" / "ignore.json"
        with patch.object(IgnoreManager, "get_ignore_file_path", return_value=nested):
            result = IgnoreManager.save_ignored_mods({"mod.a"})
        assert result is True
        assert nested.exists()


class TestAddRemoveMods:
    def test_add_single_mod(self, ignore_file: Path) -> None:
        assert IgnoreManager.add_ignored_mod("mod.a") is True
        assert IgnoreManager.is_mod_ignored("mod.a") is True

    def test_add_duplicate_is_idempotent(self, ignore_file: Path) -> None:
        IgnoreManager.add_ignored_mod("mod.a")
        assert IgnoreManager.add_ignored_mod("mod.a") is True
        assert IgnoreManager.get_ignored_mods_count() == 1

    def test_add_multiple_mods(self, ignore_file: Path) -> None:
        assert IgnoreManager.add_ignored_mods(["mod.a", "mod.b", "mod.c"]) is True
        assert IgnoreManager.get_ignored_mods_count() == 3

    def test_add_empty_list(self, ignore_file: Path) -> None:
        assert IgnoreManager.add_ignored_mods([]) is True

    def test_remove_single_mod(self, ignore_file: Path) -> None:
        IgnoreManager.add_ignored_mod("mod.a")
        assert IgnoreManager.remove_ignored_mod("mod.a") is True
        assert IgnoreManager.is_mod_ignored("mod.a") is False

    def test_remove_nonexistent_is_noop(self, ignore_file: Path) -> None:
        assert IgnoreManager.remove_ignored_mod("mod.nope") is True

    def test_remove_multiple_mods(self, ignore_file: Path) -> None:
        IgnoreManager.add_ignored_mods(["mod.a", "mod.b", "mod.c"])
        assert IgnoreManager.remove_ignored_mods(["mod.a", "mod.c"]) is True
        assert IgnoreManager.get_ignored_mods_count() == 1
        assert IgnoreManager.is_mod_ignored("mod.b") is True

    def test_clear_all(self, ignore_file: Path) -> None:
        IgnoreManager.add_ignored_mods(["mod.a", "mod.b"])
        assert IgnoreManager.clear_ignored_mods() is True
        assert IgnoreManager.get_ignored_mods_count() == 0
