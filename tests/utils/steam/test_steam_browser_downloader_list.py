"""Tests for SteamBrowser's downloader wait-list snapshot/restore helpers.

These back the fix that preserves the Mod Downloader's queued mods across
the browser window being closed (e.g. when a SteamCMD download starts),
instead of losing them if the download later fails.
"""

from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QListWidget

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
