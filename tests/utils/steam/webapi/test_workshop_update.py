from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from app.models.metadata.metadata_structure import AboutXmlMod, ModType
from app.utils.steam.workshop_utils import (
    WorkshopUpdateResult,
    query_workshop_update_data,
)


def _make_workshop_mod(path: str, pfid: str, mod_type: ModType) -> AboutXmlMod:
    """Create an AboutXmlMod with the given path, published_file_id, and mod_type."""
    mod = AboutXmlMod()
    mod.mod_path = Path(path)
    mod._mod_type = mod_type  # bypass the write-once setter since default is UNKNOWN
    # Set published_file_id directly in the instance __dict__ to bypass the
    # cached_property that tries to read from disk.
    mod.__dict__["published_file_id"] = pfid
    return mod


def _make_two_workshop_mods() -> dict[str, Any]:
    """Create a standard 2-mod dict for tests that need multiple workshop mods."""
    mod1 = _make_workshop_mod("/fake/workshop/111", "111", ModType.STEAM_WORKSHOP)
    mod2 = _make_workshop_mod("/fake/workshop/222", "222", ModType.STEAM_WORKSHOP)
    return {str(mod1.mod_path): mod1, str(mod2.mod_path): mod2}


class TestQueryWorkshopUpdateData:
    """Tests for query_workshop_update_data result handling."""

    def test_empty_mods_dict_returns_no_workshop_mods(self) -> None:
        """An empty mods dict should return no_workshop_mods, not 'failed'."""
        result = query_workshop_update_data({})
        assert isinstance(result, WorkshopUpdateResult)
        assert result.status == "no_workshop_mods"
        assert result.mods_checked == 0
        assert result.mods_updated == 0
        assert result.failed_pfids == []
        assert result.errors == []

    def test_mods_without_workshop_source_returns_no_workshop_mods(self) -> None:
        """Mods that are local/expansion (not STEAM_WORKSHOP or STEAM_CMD)
        should return no_workshop_mods."""
        mod1 = AboutXmlMod()
        mod1.mod_path = Path("/fake/expansion/core")
        mod1._mod_type = ModType.LUDEON
        mod1.__dict__["published_file_id"] = "12345"

        mod2 = AboutXmlMod()
        mod2.mod_path = Path("/fake/local/some_mod")
        mod2._mod_type = ModType.LOCAL
        # No published_file_id set

        mods: dict[str, Any] = {
            str(mod1.mod_path): mod1,
            str(mod2.mod_path): mod2,
        }
        result = query_workshop_update_data(mods)
        assert result.status == "no_workshop_mods"

    @patch("app.utils.steam.workshop_utils.ISteamRemoteStorage_GetPublishedFileDetails")
    def test_successful_query_returns_success(
        self, mock_get_details: MagicMock
    ) -> None:
        """All pfids queried successfully should return 'success'."""
        mock_get_details.return_value = (
            [
                {
                    "publishedfileid": "111",
                    "time_created": 1000,
                    "time_updated": 2000,
                },
                {
                    "publishedfileid": "222",
                    "time_created": 1000,
                    "time_updated": 3000,
                },
            ],
            [],  # no failed pfids
            [],  # no errors
        )
        mod1 = _make_workshop_mod("/fake/workshop/111", "111", ModType.STEAM_WORKSHOP)
        mod2 = _make_workshop_mod("/fake/steamcmd/222", "222", ModType.STEAM_CMD)
        mods: dict[str, Any] = {
            str(mod1.mod_path): mod1,
            str(mod2.mod_path): mod2,
        }

        mock_controller = MagicMock()
        result = query_workshop_update_data(mods, metadata_controller=mock_controller)
        assert result.status == "success"
        assert result.mods_checked == 2
        assert result.mods_updated == 2
        assert result.failed_pfids == []
        assert result.errors == []
        # Verify timestamps were written to the controller
        assert mock_controller.update_workshop_timestamps.call_count == 2

    @patch("app.utils.steam.workshop_utils.ISteamRemoteStorage_GetPublishedFileDetails")
    def test_partial_failure_returns_partial(self, mock_get_details: MagicMock) -> None:
        """Some pfids failed but some succeeded -> partial status."""
        mock_get_details.return_value = (
            [
                {
                    "publishedfileid": "111",
                    "time_created": 1000,
                    "time_updated": 2000,
                },
            ],
            ["222"],  # one failed pfid
            ["Connection timed out for 1 mods after 3 attempts"],
        )
        result = query_workshop_update_data(_make_two_workshop_mods())
        assert result.status == "partial"
        assert result.mods_checked == 2
        assert result.mods_updated == 1
        assert result.failed_pfids == ["222"]
        assert len(result.errors) == 1

    @patch("app.utils.steam.workshop_utils.ISteamRemoteStorage_GetPublishedFileDetails")
    def test_total_failure_returns_failed(self, mock_get_details: MagicMock) -> None:
        """All pfids failed -> failed status."""
        mock_get_details.return_value = (
            [],  # no metadata
            ["111", "222"],
            ["Steam API returned HTTP 503 for 2 mods after 3 attempts"],
        )
        result = query_workshop_update_data(_make_two_workshop_mods())
        assert result.status == "failed"
        assert result.mods_checked == 2
        assert result.mods_updated == 0
        assert len(result.errors) == 1

    @patch("app.utils.steam.workshop_utils.ISteamRemoteStorage_GetPublishedFileDetails")
    def test_no_controller_skips_timestamp_write(
        self, mock_get_details: MagicMock
    ) -> None:
        """When metadata_controller is None, no timestamp writing is attempted."""
        mock_get_details.return_value = (
            [
                {
                    "publishedfileid": "111",
                    "time_created": 1000,
                    "time_updated": 2000,
                },
            ],
            [],
            [],
        )
        mod1 = _make_workshop_mod("/fake/workshop/111", "111", ModType.STEAM_WORKSHOP)
        mods: dict[str, Any] = {str(mod1.mod_path): mod1}

        # Should not raise even without a controller
        result = query_workshop_update_data(mods, metadata_controller=None)
        assert result.status == "success"
        assert result.mods_updated == 1
