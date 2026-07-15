"""Tests for check_if_pfids_blacklisted in workshop_utils."""

from unittest.mock import patch

from app.models.metadata.metadata_structure import SteamDbEntry, SteamDbEntryBlacklist
from app.utils.steam.workshop_utils import check_if_pfids_blacklisted

DIALOGUE_PATH = "app.utils.steam.workshop_utils.show_dialogue_conditional"
WARNING_PATH = "app.utils.steam.workshop_utils.show_warning"


def _make_entry(
    *,
    blacklisted: bool = False,
    comment: str = "",
    name: str = "Test Mod",
) -> SteamDbEntry:
    return SteamDbEntry(
        steamName=name,
        blacklist=SteamDbEntryBlacklist(value=blacklisted, comment=comment),
    )


class TestCheckIfPfidsBlacklisted:
    def test_no_steamdb_warns_and_returns_all(self) -> None:
        pfids = ["111", "222"]
        with patch(WARNING_PATH) as mock_warn:
            result = check_if_pfids_blacklisted(pfids, {})
        mock_warn.assert_called_once()
        assert result == ["111", "222"]

    def test_no_blacklisted_mods_returns_all(self) -> None:
        db = {
            "111": _make_entry(),
            "222": _make_entry(),
        }
        result = check_if_pfids_blacklisted(["111", "222"], db)
        assert result == ["111", "222"]

    def test_unknown_pfids_pass_through(self) -> None:
        db = {"111": _make_entry()}
        result = check_if_pfids_blacklisted(["111", "999"], db)
        assert result == ["111", "999"]

    def test_skip_removes_blacklisted(self) -> None:
        db = {
            "111": _make_entry(),
            "222": _make_entry(blacklisted=True, comment="malware"),
            "333": _make_entry(),
        }
        with patch(DIALOGUE_PATH, return_value="Skip blacklisted mods"):
            result = check_if_pfids_blacklisted(["111", "222", "333"], db)
        assert "222" not in result
        assert result == ["111", "333"]

    def test_download_keeps_blacklisted(self) -> None:
        db = {
            "111": _make_entry(),
            "222": _make_entry(blacklisted=True, comment="stolen"),
        }
        with patch(DIALOGUE_PATH, return_value="Download blacklisted mods"):
            result = check_if_pfids_blacklisted(["111", "222"], db)
        assert result == ["111", "222"]

    def test_multiple_blacklisted_all_removed_on_skip(self) -> None:
        db = {
            "111": _make_entry(blacklisted=True, comment="bad"),
            "222": _make_entry(blacklisted=True, comment="worse"),
            "333": _make_entry(),
        }
        with patch(DIALOGUE_PATH, return_value="Skip blacklisted mods"):
            result = check_if_pfids_blacklisted(["111", "222", "333"], db)
        assert result == ["333"]

    def test_blacklist_false_not_flagged(self) -> None:
        db = {"111": _make_entry(blacklisted=False)}
        result = check_if_pfids_blacklisted(["111"], db)
        assert result == ["111"]
