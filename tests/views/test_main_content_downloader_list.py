"""Tests for preserving the Mod Downloader wait-list across SteamCMD runs.

Covers the fix in MainContent that snapshots the browser's queued mods
before the browser window closes (which used to wipe them out unconditionally
via SteamBrowser.closeEvent), restores them if the Mod Downloader is
reopened, and drops individual mods once SteamCMD confirms they downloaded.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.views.main_content_panel import MainContent


class TestDefensiveCopyAgainstBrowserTeardown:
    """publishedfileids can be the same list object SteamBrowser holds as
    downloader_list_mods_tracking (the download button emits it directly).
    Closing the browser clears that list in place, so it must be copied
    before the browser closes or the download silently gets an empty list.
    """

    def test_download_uses_full_list_even_if_browser_close_clears_the_source(
        self,
        main_content: tuple[MainContent, list[bool]],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        mc, _ = main_content
        steamcmd_exe = tmp_path / "steamcmd.exe"
        steamcmd_exe.write_text("")
        mc.steamcmd_wrapper.steamcmd = str(steamcmd_exe)

        monkeypatch.setattr("app.views.main_content_panel.RunnerPanel", MagicMock())

        # Simulate SteamBrowser: the button emits its tracking list directly,
        # and closing the window clears that same list object in place.
        shared_list = ["111", "222", "333"]
        mock_browser = MagicMock()
        mock_browser.get_download_list_snapshot.return_value = {
            "111": "Mod A",
            "222": "Mod B",
            "333": "Mod C",
        }
        mock_browser.close.side_effect = shared_list.clear
        mc.steam_browser = mock_browser

        mc._do_download_mods_with_steamcmd(shared_list)

        download_kwargs = mc.steamcmd_wrapper.download_mods.call_args.kwargs  # type: ignore[attr-defined]
        assert download_kwargs["publishedfileids"] == ["111", "222", "333"]

    def test_snapshot_is_captured_before_browser_closes(
        self,
        main_content: tuple[MainContent, list[bool]],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        mc, _ = main_content
        steamcmd_exe = tmp_path / "steamcmd.exe"
        steamcmd_exe.write_text("")
        mc.steamcmd_wrapper.steamcmd = str(steamcmd_exe)

        monkeypatch.setattr("app.views.main_content_panel.RunnerPanel", MagicMock())

        mock_browser = MagicMock()
        mock_browser.get_download_list_snapshot.return_value = {"111": "Mod A"}
        mc.steam_browser = mock_browser

        mc._do_download_mods_with_steamcmd(["111"])

        assert mc._pending_downloader_snapshot == {"111": "Mod A"}


class TestOnSteamcmdModDownloadSucceeded:
    """A mod that finishes downloading should stop being tracked as pending,
    whether the Mod Downloader is currently closed (state lives in the
    snapshot) or was reopened while the download was still running (state
    now lives in the live browser's own list).
    """

    def _make_bare_main_content(self) -> MainContent:
        mc = MainContent.__new__(MainContent)
        mc._pending_downloader_snapshot = {}
        mc.steam_browser = None
        return mc

    def test_pops_from_pending_snapshot_when_browser_is_closed(self) -> None:
        mc = self._make_bare_main_content()
        mc._pending_downloader_snapshot = {"111": "Mod A", "222": "Mod B"}

        mc._on_steamcmd_mod_download_succeeded("111")

        assert mc._pending_downloader_snapshot == {"222": "Mod B"}

    def test_removes_from_live_browser_when_reopened(self) -> None:
        mc = self._make_bare_main_content()
        # Snapshot already handed off to the freshly reopened browser.
        mc._pending_downloader_snapshot = {}
        mock_browser = MagicMock()
        mock_browser.downloader_list_mods_tracking = ["111", "222"]
        mc.steam_browser = mock_browser

        mc._on_steamcmd_mod_download_succeeded("111")

        mock_browser._remove_mod_from_list.assert_called_once_with("111")

    def test_does_not_touch_live_browser_for_unrelated_mod(self) -> None:
        mc = self._make_bare_main_content()
        mock_browser = MagicMock()
        mock_browser.downloader_list_mods_tracking = ["999"]
        mc.steam_browser = mock_browser

        mc._on_steamcmd_mod_download_succeeded("111")

        mock_browser._remove_mod_from_list.assert_not_called()


class TestOpenSteamBrowserRestoresPendingSnapshot:
    def test_restores_snapshot_into_freshly_created_browser(
        self,
        main_content: tuple[MainContent, list[bool]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mc, _ = main_content
        mc.steam_browser = None
        mc._pending_downloader_snapshot = {"111": "Mod A", "222": "Mod B"}

        mock_new_browser = MagicMock()
        monkeypatch.setattr(
            "app.views.main_content_panel.SteamBrowser",
            MagicMock(return_value=mock_new_browser),
        )

        mc._open_steam_browser("https://steamcommunity.com/workshop/")

        mock_new_browser.restore_download_list.assert_called_once_with(
            {"111": "Mod A", "222": "Mod B"}
        )
        assert mc._pending_downloader_snapshot == {}

    def test_skips_restore_when_no_pending_snapshot(
        self,
        main_content: tuple[MainContent, list[bool]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mc, _ = main_content
        mc.steam_browser = None
        mc._pending_downloader_snapshot = {}

        mock_new_browser = MagicMock()
        monkeypatch.setattr(
            "app.views.main_content_panel.SteamBrowser",
            MagicMock(return_value=mock_new_browser),
        )

        mc._open_steam_browser("https://steamcommunity.com/workshop/")

        mock_new_browser.restore_download_list.assert_not_called()
