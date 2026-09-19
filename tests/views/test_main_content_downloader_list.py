"""Tests for preserving the Mod Downloader wait-list across SteamCMD and
Steamworks operations.

Covers the fix in MainContent that snapshots the browser's queued mods
whenever it's about to close (which used to wipe them out unconditionally
via SteamBrowser.closeEvent, no matter what triggered the close), restores
them if the Mod Downloader is reopened, and drops individual mods once
SteamCMD confirms they downloaded or a Steamworks operation completes.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.views.main_content_panel import MainContent


def _make_ready_for_steamcmd_download(
    mc: MainContent, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Point steamcmd_wrapper.steamcmd at a real (empty) file so the
    "SteamCMD executable found" check passes, and swap out RunnerPanel so
    no real download window gets constructed.
    """
    steamcmd_exe = tmp_path / "steamcmd.exe"
    steamcmd_exe.write_text("")
    mc.steamcmd_wrapper.steamcmd = str(steamcmd_exe)
    monkeypatch.setattr("app.views.main_content_panel.RunnerPanel", MagicMock())


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
        _make_ready_for_steamcmd_download(mc, monkeypatch, tmp_path)

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


class TestSnapshotDownloaderList:
    """_snapshot_downloader_list backs SteamBrowser.about_to_close: it must
    capture the live browser's wait-list no matter what triggers the close
    (a download starting, or the user just closing the window), so a
    download still in progress never loses track of its remaining mods.
    """

    def test_captures_live_browser_state(self) -> None:
        mc = MainContent.__new__(MainContent)
        mc._pending_downloader_snapshot = {}
        mock_browser = MagicMock()
        mock_browser.get_download_list_snapshot.return_value = {"111": "Mod A"}
        mc.steam_browser = mock_browser

        mc._snapshot_downloader_list()

        assert mc._pending_downloader_snapshot == {"111": "Mod A"}

    def test_merges_with_any_existing_pending_entries(self) -> None:
        mc = MainContent.__new__(MainContent)
        mc._pending_downloader_snapshot = {"999": "Mod Z"}
        mock_browser = MagicMock()
        mock_browser.get_download_list_snapshot.return_value = {"111": "Mod A"}
        mc.steam_browser = mock_browser

        mc._snapshot_downloader_list()

        assert mc._pending_downloader_snapshot == {"999": "Mod Z", "111": "Mod A"}

    def test_noop_when_browser_is_closed(self) -> None:
        mc = MainContent.__new__(MainContent)
        mc._pending_downloader_snapshot = {"111": "Mod A"}
        mc.steam_browser = None

        mc._snapshot_downloader_list()

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
        mc.steam_browser = mock_browser

        mc._on_steamcmd_mod_download_succeeded("111")

        # Whether "111" is actually still queued in this browser is
        # remove_mod_if_queued's own concern (see test_steam_browser_downloader_list.py).
        mock_browser.remove_mod_if_queued.assert_called_once_with("111")

    def test_does_nothing_to_browser_when_none_is_open(self) -> None:
        mc = self._make_bare_main_content()
        mc._pending_downloader_snapshot = {"111": "Mod A"}

        mc._on_steamcmd_mod_download_succeeded("111")  # must not raise

        assert mc._pending_downloader_snapshot == {}


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

    def test_wires_about_to_close_to_resnapshot_the_live_list(
        self,
        main_content: tuple[MainContent, list[bool]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regression test: if the user reopens the Mod Downloader and closes
        it again while SteamCMD is still running, the restored (and possibly
        further-edited) live list must be re-captured before it's cleared,
        or a failure discovered later has nothing left to report into.
        """
        mc, _ = main_content
        mc.steam_browser = None
        mc._pending_downloader_snapshot = {}

        mock_new_browser = MagicMock()
        monkeypatch.setattr(
            "app.views.main_content_panel.SteamBrowser",
            MagicMock(return_value=mock_new_browser),
        )

        mc._open_steam_browser("https://steamcommunity.com/workshop/")

        mock_new_browser.about_to_close.connect.assert_called_once_with(
            mc._snapshot_downloader_list
        )


class TestSteamworksSubscribeSnapshotCleanup:
    """Steamworks subscribe/unsubscribe has no per-mod success/failure
    reporting the way SteamCMD does, so once the operation returns, every
    mod it covered should stop being preserved as "pending" or it would
    keep reappearing (and be re-submittable) in the reopened wait-list.
    """

    def test_completed_ids_are_dropped_from_pending_snapshot(
        self,
        main_content: tuple[MainContent, list[bool]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mc, _ = main_content
        mc.steam_browser = None
        mc._pending_downloader_snapshot = {
            "111": "Mod A",
            "222": "Mod B",
            "333": "Mod C",
        }
        monkeypatch.setattr(
            mc, "do_threaded_loading_animation", MagicMock(return_value=True)
        )
        monkeypatch.setattr(mc, "_do_refresh", MagicMock())

        mc._do_steamworks_api_call_animated(["unsubscribe", ["111", "222"]])

        assert mc._pending_downloader_snapshot == {"333": "Mod C"}

    def test_unrelated_pending_ids_are_left_alone(
        self,
        main_content: tuple[MainContent, list[bool]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mc, _ = main_content
        mc.steam_browser = None
        mc._pending_downloader_snapshot = {"333": "Mod C"}
        monkeypatch.setattr(
            mc, "do_threaded_loading_animation", MagicMock(return_value=True)
        )
        monkeypatch.setattr(mc, "_do_refresh", MagicMock())

        mc._do_steamworks_api_call_animated(["unsubscribe", ["111"]])

        assert mc._pending_downloader_snapshot == {"333": "Mod C"}

    def test_ids_are_kept_when_the_call_was_not_dispatched(
        self,
        main_content: tuple[MainContent, list[bool]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """E.g. check_steam_available() returned False and
        _do_steamworks_api_call early-returned without doing anything -
        the mods were never actually (un)subscribed, so they must not be
        dropped from the preserved wait-list.
        """
        mc, _ = main_content
        mc.steam_browser = None
        mc._pending_downloader_snapshot = {"111": "Mod A", "222": "Mod B"}
        monkeypatch.setattr(
            mc, "do_threaded_loading_animation", MagicMock(return_value=False)
        )
        monkeypatch.setattr(mc, "_do_refresh", MagicMock())

        mc._do_steamworks_api_call_animated(["unsubscribe", ["111", "222"]])

        assert mc._pending_downloader_snapshot == {"111": "Mod A", "222": "Mod B"}


class TestFailedSteamcmdRunPreservesFullSnapshotThroughReopen:
    """Closer to end-to-end: a SteamCMD run that never reports a single
    success (e.g. it crashed outright, or every mod failed) must leave the
    entire original wait-list intact and restorable, not just whichever
    mods happened to be popped off individually.
    """

    def test_full_list_survives_close_and_reopen_with_no_successes(
        self,
        main_content: tuple[MainContent, list[bool]],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        mc, _ = main_content
        _make_ready_for_steamcmd_download(mc, monkeypatch, tmp_path)

        # Mirror what SteamBrowser.closeEvent actually does: emit
        # about_to_close (here, just call the connected slot directly)
        # before the list would be cleared.
        mock_browser = MagicMock()
        mock_browser.get_download_list_snapshot.return_value = {
            "111": "Mod A",
            "222": "Mod B",
            "333": "Mod C",
        }
        mock_browser.close.side_effect = mc._snapshot_downloader_list
        mc.steam_browser = mock_browser

        mc._do_download_mods_with_steamcmd(["111", "222", "333"])

        # SteamCMD fails entirely: no steamcmd_mod_download_succeeded
        # signals ever fire, so nothing gets popped from the snapshot.

        # Reopen the Mod Downloader.
        mc.steam_browser = None
        mock_new_browser = MagicMock()
        monkeypatch.setattr(
            "app.views.main_content_panel.SteamBrowser",
            MagicMock(return_value=mock_new_browser),
        )

        mc._open_steam_browser("https://steamcommunity.com/workshop/")

        mock_new_browser.restore_download_list.assert_called_once_with(
            {"111": "Mod A", "222": "Mod B", "333": "Mod C"}
        )
