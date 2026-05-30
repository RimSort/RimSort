"""Tests for _get_missing_publishfieldid_uuids data_source filtering."""

from unittest.mock import MagicMock, patch

from app.views.main_content_panel import MainContent


@patch("app.views.main_content_panel.IgnoreManager.load_ignored_mods", return_value={})
def test_only_flags_workshop_mods(_mock_ignore: MagicMock) -> None:
    """Local and expansion mods should never be flagged."""
    panel = MagicMock(spec=MainContent)
    panel.metadata_manager = MagicMock()
    panel.metadata_manager.internal_local_metadata = {
        "uuid-workshop-missing": {
            "packageid": "author.workshopmod",
            "data_source": "workshop",
            "publishedfileid": None,
        },
        "uuid-workshop-has-pfid": {
            "packageid": "author.workshopmod2",
            "data_source": "workshop",
            "publishedfileid": "12345",
        },
        "uuid-local-missing": {
            "packageid": "author.localmod",
            "data_source": "local",
            "publishedfileid": None,
        },
        "uuid-expansion": {
            "packageid": "author.dlc",
            "data_source": "expansion",
            "publishedfileid": None,
        },
    }

    result = MainContent._get_missing_publishfieldid_uuids(panel)

    assert "uuid-workshop-missing" in result
    assert "uuid-local-missing" not in result
    assert "uuid-expansion" not in result
    assert "uuid-workshop-has-pfid" not in result


@patch("app.views.main_content_panel.IgnoreManager.load_ignored_mods", return_value={})
def test_no_workshop_mods_returns_empty(_mock_ignore: MagicMock) -> None:
    """If all mods are local/expansion, result should be empty."""
    panel = MagicMock(spec=MainContent)
    panel.metadata_manager = MagicMock()
    panel.metadata_manager.internal_local_metadata = {
        "uuid-local": {
            "packageid": "author.localmod",
            "data_source": "local",
            "publishedfileid": None,
        },
    }

    result = MainContent._get_missing_publishfieldid_uuids(panel)

    assert result == []
