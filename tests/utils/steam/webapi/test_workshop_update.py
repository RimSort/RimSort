from typing import Any
from unittest.mock import MagicMock, patch

from app.utils.metadata import WorkshopUpdateResult, query_workshop_update_data


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
        """Mods that are local/expansion (no steamcmd or workshop data_source)
        should return no_workshop_mods."""
        mods = {
            "uuid-1": {
                "packageid": "core",
                "data_source": "expansion",
                "publishedfileid": "12345",
            },
            "uuid-2": {
                "packageid": "some.local.mod",
                "data_source": "local",
            },
        }
        result = query_workshop_update_data(mods)
        assert result.status == "no_workshop_mods"

    @patch("app.utils.metadata.ISteamRemoteStorage_GetPublishedFileDetails")
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
        mods: dict[str, Any] = {
            "uuid-1": {
                "data_source": "workshop",
                "publishedfileid": "111",
            },
            "uuid-2": {
                "steamcmd": True,
                "publishedfileid": "222",
            },
        }
        result = query_workshop_update_data(mods)
        assert result.status == "success"
        assert result.mods_checked == 2
        assert result.mods_updated == 2
        assert result.failed_pfids == []
        assert result.errors == []
        # Verify update data was written back to mods dict
        assert mods["uuid-1"]["external_time_updated"] == 2000
        assert mods["uuid-2"]["external_time_updated"] == 3000

    @patch("app.utils.metadata.ISteamRemoteStorage_GetPublishedFileDetails")
    def test_partial_failure_returns_partial(self, mock_get_details: MagicMock) -> None:
        """Some pfids failed but some succeeded → partial status."""
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
        mods = {
            "uuid-1": {
                "data_source": "workshop",
                "publishedfileid": "111",
            },
            "uuid-2": {
                "data_source": "workshop",
                "publishedfileid": "222",
            },
        }
        result = query_workshop_update_data(mods)
        assert result.status == "partial"
        assert result.mods_checked == 2
        assert result.mods_updated == 1
        assert result.failed_pfids == ["222"]
        assert len(result.errors) == 1

    @patch("app.utils.metadata.ISteamRemoteStorage_GetPublishedFileDetails")
    def test_total_failure_returns_failed(self, mock_get_details: MagicMock) -> None:
        """All pfids failed → failed status."""
        mock_get_details.return_value = (
            [],  # no metadata
            ["111", "222"],
            ["Steam API returned HTTP 503 for 2 mods after 3 attempts"],
        )
        mods = {
            "uuid-1": {
                "data_source": "workshop",
                "publishedfileid": "111",
            },
            "uuid-2": {
                "data_source": "workshop",
                "publishedfileid": "222",
            },
        }
        result = query_workshop_update_data(mods)
        assert result.status == "failed"
        assert result.mods_checked == 2
        assert result.mods_updated == 0
        assert len(result.errors) == 1
