from typing import Any
from unittest.mock import MagicMock, patch

from app.utils.schema import generate_rimworld_mods_list, validate_rimworld_mods_list


class TestGenerateRimworldModsList:
    def test_basic_generation(self) -> None:
        result = generate_rimworld_mods_list(
            "1.5",
            ["ludeon.rimworld", "brrainz.harmony"],
        )
        assert result["ModsConfigData"]["version"] == "1.5"
        active = result["ModsConfigData"]["activeMods"]["li"]
        assert active == ["ludeon.rimworld", "brrainz.harmony"]

    def test_known_expansions_excludes_base_game(self) -> None:
        result = generate_rimworld_mods_list(
            "1.5",
            ["ludeon.rimworld"],
            dlc_ids=["ludeon.rimworld", "ludeon.rimworld.royalty"],
        )
        known = result["ModsConfigData"]["knownExpansions"]["li"]
        assert "ludeon.rimworld" not in known
        assert "ludeon.rimworld.royalty" in known

    def test_empty_packageids(self) -> None:
        result = generate_rimworld_mods_list("1.5", [])
        assert result["ModsConfigData"]["activeMods"]["li"] == []


class TestValidateRimworldModsList:
    @patch("app.utils.schema.show_warning")
    def test_modsconfig_format(self, mock_warn: MagicMock, qapp: Any) -> None:
        data = {
            "ModsConfigData": {
                "activeMods": {"li": ["ludeon.rimworld", "brrainz.harmony"]}
            }
        }
        result = validate_rimworld_mods_list(data)
        assert result == ["ludeon.rimworld", "brrainz.harmony"]
        mock_warn.assert_not_called()

    @patch("app.utils.schema.show_warning")
    def test_modsconfig_single_mod_string(
        self, mock_warn: MagicMock, qapp: Any
    ) -> None:
        data = {"ModsConfigData": {"activeMods": {"li": "ludeon.rimworld"}}}
        result = validate_rimworld_mods_list(data)
        assert result == ["ludeon.rimworld"]
        mock_warn.assert_not_called()

    @patch("app.utils.schema.show_warning")
    def test_savegame_format(self, mock_warn: MagicMock, qapp: Any) -> None:
        data = {"savegame": {"meta": {"modIds": {"li": ["ludeon.rimworld"]}}}}
        result = validate_rimworld_mods_list(data)
        assert result == ["ludeon.rimworld"]
        mock_warn.assert_not_called()

    @patch("app.utils.schema.show_warning")
    def test_saved_mod_list_format(self, mock_warn: MagicMock, qapp: Any) -> None:
        data = {"savedModList": {"meta": {"modIds": {"li": ["ludeon.rimworld"]}}}}
        result = validate_rimworld_mods_list(data)
        assert result == ["ludeon.rimworld"]
        mock_warn.assert_not_called()

    @patch("app.utils.schema.show_warning")
    def test_invalid_format_returns_default(
        self, mock_warn: MagicMock, qapp: Any
    ) -> None:
        result = validate_rimworld_mods_list({"garbage": "data"})
        assert result == ["Ludeon.RimWorld"]
        mock_warn.assert_called_once()
