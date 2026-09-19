"""Tests for SteamBrowser's downloader wait-list snapshot/restore helpers.

These back the fix that preserves the Mod Downloader's queued mods across
the browser window being closed (e.g. when a SteamCMD download starts),
instead of losing them if the download later fails.
"""

from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem

from app.utils.steam.steambrowser.browser import SteamBrowser


def _make_browser() -> SteamBrowser:
    """A bare SteamBrowser with just the attributes _add_mod_to_list needs."""
    browser = SteamBrowser.__new__(SteamBrowser)
    browser.downloader_list = QListWidget()
    browser.downloader_list_mods_tracking = []
    browser.downloader_list_dupe_tracking = {}
    browser.current_title = "RimSort - Steam Browser"
    browser.current_url = ""
    browser.url_prefix_sharedfiles = (
        "https://steamcommunity.com/sharedfiles/filedetails/?id="
    )
    browser.web_view = MagicMock()
    return browser


class TestGetDownloadListSnapshot:
    def test_captures_pfid_to_title_for_each_queued_mod(
        self, qapp: QApplication
    ) -> None:
        browser = _make_browser()
        browser._add_mod_to_list("111", title="Mod A")
        browser._add_mod_to_list("222", title="Mod B")

        assert browser.get_download_list_snapshot() == {
            "111": "Mod A",
            "222": "Mod B",
        }

    def test_empty_list_yields_empty_snapshot(self, qapp: QApplication) -> None:
        browser = _make_browser()

        assert browser.get_download_list_snapshot() == {}

    def test_skips_items_with_no_pfid_data(self, qapp: QApplication) -> None:
        """An item with no UserRole data (publishedfileid is None) must not
        become a dict key, despite the dict[str, str] annotation.
        """
        browser = _make_browser()
        browser._add_mod_to_list("111", title="Mod A")
        browser.downloader_list.addItem(QListWidgetItem("no pfid set"))

        assert browser.get_download_list_snapshot() == {"111": "Mod A"}


class TestAddModToListNormalizesPfid:
    """Collection adds come from Steam's WebAPI JSON, which returns
    publishedfileid as a number, while JS-bridge/URL adds already pass a
    str. Both must end up comparable as str, or a collection-queued mod's
    int key would never match a SteamCMD success line's str pfid.
    """

    def test_int_pfid_is_stored_as_str(self, qapp: QApplication) -> None:
        browser = _make_browser()

        browser._add_mod_to_list(111, title="Mod A")  # type: ignore[arg-type]

        assert browser.downloader_list_mods_tracking == ["111"]
        assert browser.get_download_list_snapshot() == {"111": "Mod A"}

    def test_int_and_str_pfid_for_same_mod_are_treated_as_duplicates(
        self, qapp: QApplication
    ) -> None:
        browser = _make_browser()

        browser._add_mod_to_list(111, title="Mod A")  # type: ignore[arg-type]
        browser._add_mod_to_list("111", title="Mod A")

        assert browser.downloader_list_mods_tracking == ["111"]
        assert browser.downloader_list.count() == 1


class TestRemoveModIfQueued:
    def test_removes_a_queued_mod(self, qapp: QApplication) -> None:
        browser = _make_browser()
        browser._add_mod_to_list("111", title="Mod A")

        browser.remove_mod_if_queued("111")

        assert browser.downloader_list_mods_tracking == []
        assert browser.downloader_list.count() == 0

    def test_is_a_quiet_noop_for_an_unqueued_mod(self, qapp: QApplication) -> None:
        browser = _make_browser()
        browser._add_mod_to_list("999", title="Mod Z")

        browser.remove_mod_if_queued("111")  # must not raise

        assert browser.downloader_list_mods_tracking == ["999"]


class TestRestoreDownloadList:
    def test_repopulates_tracking_and_ui(self, qapp: QApplication) -> None:
        browser = _make_browser()
        snapshot = {"111": "Mod A", "222": "Mod B"}

        browser.restore_download_list(snapshot)

        assert browser.downloader_list_mods_tracking == ["111", "222"]
        assert browser.downloader_list.count() == 2

    def test_round_trip_through_snapshot_and_restore(self, qapp: QApplication) -> None:
        source = _make_browser()
        source._add_mod_to_list("111", title="Mod A")
        source._add_mod_to_list("222", title="Mod B")
        snapshot = source.get_download_list_snapshot()

        destination = _make_browser()
        destination.restore_download_list(snapshot)

        assert destination.get_download_list_snapshot() == snapshot
